import argparse
import asyncio
import os
import sys
from pathlib import Path

# Tambahkan root direktori ke sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.repositories.knowledge_repo import KnowledgeRepo
from app.schemas.rag import DocumentIn
from app.services.rag_service import ingest

DEFAULT_SKILLS_DIR = Path(__file__).resolve().parent.parent / ".agents" / "skills"

CATEGORY_MAP = {
    "xss": "xss",
    "sqli": "sqli",
    "sql-injection": "sqli",
    "idor": "idor",
}

def resolve_category(name: str) -> str:
    name_lower = name.lower()
    for key, cat in CATEGORY_MAP.items():
        if key in name_lower:
            return cat
    return "general"

def collect_skill_files(skills_dir: Path) -> list[tuple[str, Path]]:
    results = []
    if not skills_dir.exists():
        return results
    for item in sorted(skills_dir.iterdir()):
        if item.is_dir():
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                results.append((item.name, skill_md))
        elif item.is_file() and item.name.endswith(".md"):
            results.append((item.stem, item))
    return results

async def ingest_via_db(docs: list[DocumentIn]) -> list[dict]:
    results = []
    async with AsyncSessionLocal() as session:
        repo = KnowledgeRepo(session)
        for doc in docs:
            res = await ingest(doc, repo)
            results.append({"source": doc.source, "chunks": res.get("chunks_saved", 0), "doc_id": res.get("doc_id")})
    return results

async def ingest_via_http(docs: list[DocumentIn], base_url: str, api_key: str) -> list[dict]:
    results = []
    headers = {"X-RAG-Api-Key": api_key}
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        for doc in docs:
            resp = await client.post("/rag/documents", json=doc.model_dump(), headers=headers)
            resp.raise_for_status()
            data = resp.json()
            results.append({"source": doc.source, "chunks": data.get("chunks_saved", 0), "doc_id": data.get("doc_id")})
    return results

def prepare_documents(skill_entries: list[tuple[str, Path]], max_bytes: int = 200_000) -> list[DocumentIn]:
    documents = []
    for skill_name, file_path in skill_entries:
        raw_text = file_path.read_text(encoding="utf-8")
        raw_bytes = raw_text.encode("utf-8")
        category = resolve_category(skill_name)
        source_label = f"skills/{skill_name}"

        if len(raw_bytes) <= max_bytes:
            documents.append(
                DocumentIn(
                    title=f"Skill: {skill_name}",
                    source=source_label,
                    content=raw_text,
                    category=category,
                    trust="curated",
                )
            )
        else:
            part = 1
            start = 0
            while start < len(raw_text):
                chunk = raw_text[start : start + (max_bytes // 2)]
                documents.append(
                    DocumentIn(
                        title=f"Skill: {skill_name} (Part {part})",
                        source=f"{source_label}#part{part}",
                        content=chunk,
                        category=category,
                        trust="curated",
                    )
                )
                start += max_bytes // 2
                part += 1
    return documents

async def main_async(args: argparse.Namespace) -> None:
    skills_dir = Path(args.skills_dir)
    skill_entries = collect_skill_files(skills_dir)
    if not skill_entries:
        print(f"Tidak ada file SKILL.md ditemukan di {skills_dir}")
        return

    docs = prepare_documents(skill_entries, max_bytes=settings.rag_max_doc_bytes)
    print(f"Menyiapkan {len(docs)} dokumen dari {len(skill_entries)} skill...")

    if args.http:
        url = args.api_url.rstrip("/")
        key = args.api_key or settings.rag_api_key
        print(f"Mengirim via HTTP ke {url}...")
        results = await ingest_via_http(docs, url, key)
    else:
        print("Menyimpan langsung ke database via SQLAlchemy session...")
        results = await ingest_via_db(docs)

    total_chunks = sum(r["chunks"] for r in results)
    for r in results:
        print(f"OK: {r['source']} -> {r['chunks']} chunks (doc_id: {r['doc_id']})")
    print(f"\nSelesai. Total chunk tersimpan: {total_chunks}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest skills ke RAG knowledge base")
    parser.add_argument("--skills-dir", default=str(DEFAULT_SKILLS_DIR), help="Direktori skills")
    parser.add_argument("--http", action="store_true", help="Ingest via HTTP POST /rag/documents")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="URL API zaplang")
    parser.add_argument("--api-key", default="", help="X-RAG-Api-Key")
    args = parser.parse_args()

    try:
        asyncio.run(main_async(args))
    except Exception as exc:
        print(f"Gagal ingest skills: {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
