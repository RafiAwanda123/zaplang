# zaplang

AI-powered security testing agent that connects OWASP ZAP to LLM reasoning through the Model Context Protocol (MCP). Instead of reading raw scanner output and deciding what matters yourself, zaplang does the triage, filters noise, looks up attack techniques from a local knowledge base, and generates ready-to-run PoC commands.

Built with FastAPI, pgvector, Ollama embeddings, and FastMCP.

## What This Project Does

```
You (prompt) --> AI Agent --> MCP Server --> OWASP ZAP
                    |                           |
                    |                           v
                    |                     Scan / Spider / Alerts
                    |                           |
                    v                           v
              RAG Knowledge Base          Triage & PoC
              (pgvector + Ollama)         (7-Question Gate)
```

1. **You give a prompt** like "scan http://target.local and find vulnerabilities".
2. **The AI agent calls MCP tools** that talk to ZAP's REST API.
3. **ZAP does the scanning.** The agent reads alerts, filters out noise using the 7-Question Gate (a checklist that kills theoretical bugs), maps findings to Bugcrowd VRT severity (P1-P4), and generates curl commands you can copy-paste to verify.
4. **The RAG knowledge base** stores bug bounty techniques, bypass patterns, and methodology extracted from skill files. The agent queries it before deciding how to test a target.

Every URL passes through `enforce_scope()` before any request is made. Active scans require explicit human approval (`human_approved=True`). Data from targets is wrapped in `<untrusted_data>` tags and truncated to prevent prompt injection.

## MCP Tools

| Tool | What It Does |
|---|---|
| `zap_get_version` | Check if ZAP daemon is running and return its version. |
| `zap_spider_start` | Start a spider crawl on a scope-validated target URL. |
| `zap_spider_status` | Check spider progress (0-100%). |
| `zap_get_alerts` | Fetch ZAP alerts, deduplicate, sort by risk, sanitize output. |
| `zap_triage_alerts` | Filter alerts through the 7-Question Gate. Drop scanner noise (missing headers, banner leaks, timestamp disclosure). Map survivors to Bugcrowd VRT priority. |
| `zap_targeted_active_scan` | Run active scan on a specific endpoint. Requires `human_approved=True`. |
| `zap_ascan_status` | Check active scan progress (0-100%). |
| `zap_rag_lookup` | Search the local RAG knowledge base for techniques, bypasses, and methodology. |
| `zap_generate_poc` | Convert a ZAP alert into a minimal curl PoC command for manual verification. Supports XSS, SQLi, and IDOR templates. |
| `zap_recon_scope_triage` | Separate owned target assets from namespace collisions and third-party noise in recon/ASM output. Flags soft-404 false positives. |
| `zap_osint_fingerprint` | Passive fingerprint: detect server tech, WAF/CDN (Cloudflare, CloudFront), and security headers without sending attack payloads. |

## Project Structure

```
zaplang/
├── app/
│   ├── api/
│   │   ├── health.py          # GET /health
│   │   └── rag.py             # POST /rag/documents, POST /rag/query
│   ├── core/
│   │   ├── config.py          # Pydantic Settings (all env vars)
│   │   └── scope.py           # enforce_scope() + ScopeViolation
│   ├── db/
│   │   └── session.py         # AsyncEngine + AsyncSessionLocal
│   ├── prompts/
│   │   └── persona.yaml       # Agent persona with 7-Question Gate and VRT rules
│   ├── repositories/
│   │   └── knowledge_repo.py  # pgvector CRUD (insert_chunk, cosine_search)
│   ├── schemas/
│   │   └── rag.py             # Pydantic models (DocumentIn, QueryIn, etc.)
│   ├── services/
│   │   ├── rag_service.py     # Chunking, Ollama embedding, ingest/retrieve
│   │   ├── zap_client.py      # Async httpx client for ZAP REST API
│   │   └── agent/             # LangChain agent builder (scaffold)
│   └── main.py                # FastAPI app entrypoint
├── scripts/
│   └── ingest_skills.py       # Ingest .agents/skills/ into pgvector
├── tests/
│   ├── test_mcp_server.py     # MCP tool tests (triage, PoC, scope, RAG)
│   ├── test_rag.py            # RAG endpoint tests (auth, size limit, trust)
│   ├── test_scope.py          # Scope enforcement tests
│   └── test_ingest_skills.py  # Ingestion script tests
├── migrations/
│   └── 001_rag.sql            # pgvector schema (knowledge_chunks table)
├── .agents/skills/            # Bug bounty methodology skill files
├── mcp_server.py              # FastMCP server (11 tools)
├── docker-compose.yml         # ZAP + PostgreSQL/pgvector + FastAPI
├── .env.example               # Template for all required env vars
└── requirements.txt           # Python dependencies
```

## Prerequisites

- **Python 3.12+**
- **Docker & Docker Compose** (for ZAP and PostgreSQL/pgvector)
- **Ollama** with `nomic-embed-text` model (for local embeddings)
- An MCP-compatible AI client (Claude Desktop, Antigravity, Cursor, etc.)

## Setup

### 1. Clone and configure environment

```bash
git clone https://github.com/YOUR_USERNAME/zaplang.git
cd zaplang
cp .env.example .env
```

Edit `.env` and fill in:
- `ZAP_API_KEY` - generate one in ZAP GUI: Tools > Options > API > API Key
- `RAG_API_KEY` - any secret string you choose for RAG endpoint auth
- `ALLOWED_HOSTS` - comma-separated hostnames you are authorized to test
- `DATABASE_URL` - default works with the Docker Compose setup
- `OPENROUTER_API_KEY` - (optional) for LLM-powered agent features

### 2. Start infrastructure

```bash
# Start ZAP daemon and PostgreSQL with pgvector
docker compose up -d

# Verify ZAP is running
curl -s "http://127.0.0.1:8080/JSON/core/view/version/?apikey=YOUR_ZAP_API_KEY"
```

> **Note:** If you have a local PostgreSQL running on port 5432, stop it first:
> `sudo systemctl stop postgresql`

### 3. Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install fastmcp
```

### 4. Run database migration

```bash
docker compose exec db psql -U zaplang -d zaplang -f /dev/stdin < migrations/001_rag.sql
```

### 5. Install Ollama embedding model

```bash
ollama pull nomic-embed-text
```

### 6. Start the FastAPI server

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 7. Ingest skill files into the knowledge base

```bash
# Direct database ingestion (FastAPI server not required)
.venv/bin/python scripts/ingest_skills.py

# Or via HTTP API (FastAPI server must be running)
.venv/bin/python scripts/ingest_skills.py --http --api-key YOUR_RAG_API_KEY
```

### 8. Connect to your MCP client

Add this to your MCP client configuration (example for Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "zaplang": {
      "command": "/path/to/zaplang/.venv/bin/python",
      "args": ["/path/to/zaplang/mcp_server.py"],
      "env": {
        "ZAP_API_KEY": "your-zap-api-key",
        "ZAP_BASE": "http://127.0.0.1:8080",
        "ALLOWED_HOSTS": "target.local",
        "DATABASE_URL": "postgresql+asyncpg://zaplang:password@localhost:5432/zaplang",
        "OLLAMA_URL": "http://localhost:11434",
        "EMBED_MODEL": "nomic-embed-text",
        "RAG_API_KEY": "your-rag-api-key"
      }
    }
  }
}
```

## Usage Examples

Once connected to your MCP client, you can give natural language prompts:

```
"Check if ZAP is running"
-> Calls zap_get_version

"Spider http://target.local and show me the alerts"
-> Calls zap_spider_start, zap_spider_status, zap_get_alerts

"Triage the alerts and show only real findings"
-> Calls zap_triage_alerts (filters noise, maps to VRT severity)

"Generate a PoC for that XSS on /search?q="
-> Calls zap_generate_poc (outputs a curl command)

"Look up IDOR bypass techniques"
-> Calls zap_rag_lookup (searches pgvector knowledge base)

"Run an active scan on /api/login"
-> Calls zap_targeted_active_scan (will ask for human_approved=True)

"Fingerprint http://target.local"
-> Calls zap_osint_fingerprint (passive header analysis)
```

## Running Tests

```bash
source .venv/bin/activate
pytest tests/
```

All tests use mocks and do not require a running ZAP instance, database, or Ollama.

```
tests/test_mcp_server.py     10 tests  (triage filter, PoC gen, scope, RAG lookup, recon triage, fingerprint)
tests/test_rag.py             7 tests  (auth 401, wrong key, oversized doc 413, trust filter, chunking)
tests/test_scope.py           4 tests  (allowed host, disallowed host, bad scheme, subdomain spoof)
tests/test_ingest_skills.py   2 tests  (category resolution, oversized document splitting)
```

## Security Model

| Layer | Mechanism |
|---|---|
| **Scope enforcement** | Every URL passes through `enforce_scope()` before any HTTP request. Only hostnames listed in `ALLOWED_HOSTS` are permitted. Scheme restricted to `http`/`https`. |
| **Human approval gate** | Active scans require `human_approved=True`. The LLM cannot grant this on its own. |
| **Untrusted data isolation** | All target-sourced data (URLs, evidence, descriptions) is wrapped in `<untrusted_data>` tags, control characters stripped, and truncated to prevent prompt injection. |
| **API key protection** | ZAP key sent via `X-ZAP-Api-Key` header (never in query string). RAG key validated server-side. No keys are logged or printed. |
| **Alert triage** | The 7-Question Gate eliminates theoretical bugs, scanner noise, and always-rejected findings before they reach the report. |

## Skill Files

The `.agents/skills/` directory contains curated methodology documents that get ingested into the RAG knowledge base:

| Skill | Content |
|---|---|
| `bug-bounty` | Full pipeline: recon, hunting (IDOR/XSS/SSRF/SQLi/auth bypass), 7-Question Gate, validation gates, report templates, always-rejected list, A->B chain patterns. |
| `bb-metodology` | 5-phase non-linear hunting workflow, critical thinking framework, developer psychology model, Wide vs Deep route selection. |
| `bugcrowd-reporting` | Bugcrowd VRT category mapping, severity override rules, out-of-scope rebuttal patterns, report title formula. |
| `osint-methodology` | 5-stage recon pipeline, 29 asset types, identity fabric mapping, WAF/CDN bypass, vulnerability prioritization. |
| `recon-scope-triage` | Asset ownership validation, namespace collision detection, soft-404 false positive control. |
| `web2-recon` | Subdomain enumeration, URL crawling, directory fuzzing, JS analysis, continuous monitoring. |
| `scope-guardrails` | Scope validation rules, allowlist enforcement, rate limiting. |
| `untrusted-output-handling` | Indirect prompt injection defense, data wrapping rules. |
| `zap-api-tools` | ZAP REST API usage patterns and constraints. |

## Additional Documentation

| File | Description |
|---|---|
| [cheatsheet.md](cheatsheet.md) | Copy-paste Postman payloads for every API endpoint. |
| [TUTORIAL_TEST_MANUAL_ZAP_POSTMAN.md](TUTORIAL_TEST_MANUAL_ZAP_POSTMAN.md) | Step-by-step guide for manual security testing with ZAP as intercepting proxy + Postman. |

## Contributing

1. Fork the repository.
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Write tests for new MCP tools or endpoints.
4. Run `pytest tests/` and confirm all tests pass.
5. Submit a pull request.

Please follow these rules:
- Every new MCP tool must call `enforce_scope()` on target URLs.
- Active/destructive actions must require `human_approved=True`.
- Target-sourced data must be wrapped with `_sanitize_untrusted()`.
- No hardcoded API keys or credentials anywhere in the codebase.

## License

MIT
