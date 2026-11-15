import json
import logging
import re
from urllib.parse import quote_plus, urljoin
import httpx
from fastmcp import FastMCP
from app.core.config import settings
from app.core.scope import ScopeViolation, enforce_scope
from app.db.session import AsyncSessionLocal
from app.repositories.knowledge_repo import KnowledgeRepo
from app.schemas.rag import QueryIn
from app.services.rag_service import retrieve
from app.services.zap_client import ZapClient

mcp = FastMCP(
    "zap-security-scanner",
    instructions="MCP Server OWASP ZAP. Target wajib ada di ALLOWED_HOSTS.",
)

_CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_RISK_WEIGHTS = {"High": 4, "Medium": 3, "Low": 2, "Informational": 1}
_NOISE_PLUGIN_IDS = frozenset(
    {"10015", "10016", "10017", "10021", "10036", "10038", "10063", "10096", "10110"}
)
_VRT_MAP = {
    "High": "P1-P2",
    "Medium": "P2-P3",
    "Low": "P3-P4",
    "Informational": "P5-Informational",
}

def _sanitize_untrusted(text: str, max_chars: int = 200) -> str:
    if not text:
        return ""
    cleaned = _CONTROL_CHAR_REGEX.sub(" ", text)[:max_chars].strip()
    return f"<untrusted_data>{cleaned}</untrusted_data>"

@mcp.tool()
async def zap_get_version() -> str:
    """Cek versi dan status ZAP daemon."""
    try:
        async with ZapClient() as client:
            version = await client.version()
            return f"ZAP aktif: v{version}"
    except Exception as e:
        return f"Gagal koneksi ZAP: {e}"

@mcp.tool()
async def zap_spider_start(target_url: str, subtree_only: bool = True) -> str:
    """Mulai spider scan URL target (tervalidasi scope)."""
    try:
        async with ZapClient() as client:
            scan_id = await client.spider_start(target_url, subtree_only=subtree_only)
            return f"Spider dimulai di {target_url}. Scan ID: {scan_id}"
    except ScopeViolation as e:
        return f"BLOCKED: {e.reason}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def zap_spider_status(scan_id: str) -> str:
    """Cek progress spider scan (0-100%)."""
    try:
        async with ZapClient() as client:
            progress = await client.spider_status(scan_id)
            return f"Status spider {scan_id}: {progress}%" if progress < 100 else f"Spider {scan_id} selesai (100%)."
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def zap_get_alerts(base_url: str = "", count: int = 50) -> str:
    """Ambil alert keamanan ZAP yang telah disanitasi."""
    try:
        async with ZapClient() as client:
            raw_alerts = await client.alerts(base_url=base_url, count=count)
            if not raw_alerts:
                return "Tidak ada alert."

            sorted_alerts = sorted(
                raw_alerts,
                key=lambda a: _RISK_WEIGHTS.get(a.get("risk", ""), 0),
                reverse=True,
            )

            lines = [f"Total {len(sorted_alerts)} alert:"]
            seen = set()
            for a in sorted_alerts:
                key = (a.get("pluginId"), a.get("alert"), a.get("url"))
                if key in seen:
                    continue
                seen.add(key)
                lines.append(
                    f"\n[{a.get('risk', 'UNKNOWN').upper()}] {a.get('alert', '')}\n"
                    f"- URL: {_sanitize_untrusted(a.get('url', ''))}\n"
                    f"- Bukti: {_sanitize_untrusted(a.get('evidence', ''), 150)}\n"
                    f"- Deskripsi: {_sanitize_untrusted(a.get('description', ''), 150)}"
                )
            return "\n".join(lines)
    except ScopeViolation as e:
        return f"BLOCKED: {e.reason}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def zap_triage_alerts(base_url: str = "", count: int = 50) -> str:
    """Triage alert dengan filter 7-Question Gate dan pemetaan VRT."""
    try:
        async with ZapClient() as client:
            raw_alerts = await client.alerts(base_url=base_url, count=count)
            if not raw_alerts:
                return "Tidak ada alert untuk ditinjau."

            qualified = []
            seen = set()
            for a in raw_alerts:
                plugin_id = str(a.get("pluginId", ""))
                risk = a.get("risk", "Informational")
                if plugin_id in _NOISE_PLUGIN_IDS:
                    continue
                if risk == "Informational" and not a.get("evidence"):
                    continue

                key = (plugin_id, a.get("url"), a.get("param"))
                if key in seen:
                    continue
                seen.add(key)
                qualified.append(a)

            if not qualified:
                return "Semua alert tereliminasi oleh 7-Question Gate (noise/headers/low-impact)."

            qualified.sort(key=lambda a: _RISK_WEIGHTS.get(a.get("risk", ""), 0), reverse=True)

            lines = [f"Kandidat Temuan Lolos Triage (Total: {len(qualified)}):"]
            for a in qualified:
                risk = a.get("risk", "Unknown")
                vrt = _VRT_MAP.get(risk, "P4")
                lines.append(
                    f"\n[VRT {vrt}] [{risk.upper()}] {a.get('alert', '')} (Plugin: {a.get('pluginId', '')})\n"
                    f"- URL: {_sanitize_untrusted(a.get('url', ''))}\n"
                    f"- Parameter: {_sanitize_untrusted(a.get('param', ''))}\n"
                    f"- Bukti: {_sanitize_untrusted(a.get('evidence', ''), 150)}\n"
                    f"- Status: Lolos filter awal 7-Question Gate"
                )
            return "\n".join(lines)
    except ScopeViolation as e:
        return f"BLOCKED: {e.reason}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def zap_targeted_active_scan(
    target_url: str,
    endpoint_path: str = "",
    scan_policy: str = "",
    human_approved: bool = False,
) -> str:
    """Targeted active scan pada endpoint yang disetujui manusia."""
    if not human_approved:
        return "BLOCKED: Active scan memerlukan persetujuan manusia eksplisit (human_approved=True)."
    try:
        full_url = urljoin(target_url.rstrip("/") + "/", endpoint_path.lstrip("/")) if endpoint_path else target_url
        enforce_scope(full_url)
        async with ZapClient() as client:
            scan_id = await client.ascan_start(full_url, scan_policy_name=scan_policy)
            return f"Targeted active scan dimulai di {full_url}. Scan ID: {scan_id}"
    except ScopeViolation as e:
        return f"BLOCKED: {e.reason}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def zap_ascan_status(scan_id: str) -> str:
    """Cek progress active scan (0-100%)."""
    try:
        async with ZapClient() as client:
            progress = await client.ascan_status(scan_id)
            return f"Status active scan {scan_id}: {progress}%" if progress < 100 else f"Active scan {scan_id} selesai (100%)."
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def zap_rag_lookup(query: str, category: str = "") -> str:
    """Cari metodologi, teknik, dan bypass dari RAG knowledge base."""
    try:
        clean_cat = category.strip().lower()
        cat = clean_cat if clean_cat in {"xss", "idor", "sqli", "general"} else None
        query_in = QueryIn(query=query, category=cat, top_k=settings.rag_top_k, include_unverified=False)
        async with AsyncSessionLocal() as session:
            repo = KnowledgeRepo(session)
            chunks = await retrieve(query_in, repo)
            if not chunks:
                return "Tidak ada referensi relevan ditemukan di knowledge base."
            lines = [f"Ditemukan {len(chunks)} referensi:"]
            for i, c in enumerate(chunks, 1):
                clean_content = _sanitize_untrusted(c.content, 400)
                lines.append(
                    f"\n[Referensi #{i}] (Source: {c.source}, Category: {c.category}, Score: {c.score})\n"
                    f"{clean_content}"
                )
            return "\n".join(lines)
    except Exception as e:
        return f"Gagal lookup knowledge base: {e}"

@mcp.tool()
async def zap_generate_poc(
    alert_json: str = "",
    target_url: str = "",
    vuln_type: str = "xss",
    param: str = "",
    method: str = "GET",
) -> str:
    """Hasilkan perintah curl PoC minimal untuk verifikasi manual."""
    try:
        url = target_url
        p = param
        vtype = vuln_type.lower()
        m = method.upper()

        if alert_json.strip().startswith("{"):
            try:
                data = json.loads(alert_json)
                url = data.get("url") or url
                p = data.get("param") or p
                alert_name = (data.get("alert") or "").lower()
                m = (data.get("method") or m).upper()
                if "sql" in alert_name:
                    vtype = "sqli"
                elif "xss" in alert_name or "cross site" in alert_name:
                    vtype = "xss"
                elif "idor" in alert_name or "traversal" in alert_name or "path" in alert_name:
                    vtype = "idor"
            except Exception:
                pass

        if not url:
            return "Error: target_url wajib diisi atau disertakan dalam alert_json."

        enforce_scope(url)

        if vtype == "xss":
            probe = "\"><script>alert(1)</script>"
            if p:
                poc_cmd = f"curl -i -s -k -X {m} \"{url}?{p}={quote_plus(probe)}\""
            else:
                poc_cmd = f"curl -i -s -k -X {m} \"{url}?q={quote_plus(probe)}\""
            steps = "1. Jalankan curl di terminal.\n2. Cek apakah payload script direfleksikan tanpa HTML encoding."
        elif vtype == "sqli":
            probe = "' OR 1=1--"
            if p:
                poc_cmd = f"curl -i -s -k -X {m} \"{url}?{p}={quote_plus(probe)}\""
            else:
                poc_cmd = f"curl -i -s -k -X {m} \"{url}?id={quote_plus(probe)}\""
            steps = "1. Jalankan curl di terminal.\n2. Amati status code, pesan error DB, atau perbedaan panjang respons."
        elif vtype == "idor":
            poc_cmd = (
                f"# Sesi User A:\ncurl -i -s -k -H \"Authorization: Bearer <TOKEN_A>\" \"{url}\"\n\n"
                f"# Sesi User B (akses data User A):\ncurl -i -s -k -H \"Authorization: Bearer <TOKEN_B>\" \"{url}\""
            )
            steps = "1. Ambil data User A dengan token User B.\n2. Jika HTTP 200 dan data User A terbaca, IDOR valid."
        else:
            poc_cmd = f"curl -i -s -k -X {m} \"{url}\""
            steps = "1. Jalankan curl untuk memeriksa respons.\n2. Lakukan pengujian manual terarah."

        output = (
            "[PoC - Manual Verification Required]\n"
            f"Vulnerability Type: {vtype.upper()}\n"
            f"Target: {_sanitize_untrusted(url)}\n"
            f"Method: {m}\n"
            f"Command:\n{poc_cmd}\n\n"
            f"Langkah Verifikasi:\n{steps}\n\n"
            "Peringatan: Verifikasi manual wajib dilakukan. Jangan jalankan otomatis pada production."
        )
        return output
    except ScopeViolation as e:
        return f"BLOCKED: {e.reason}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def zap_recon_scope_triage(
    assets_raw: str,
    canonical_domain: str = "",
) -> str:
    """Triage aset recon/ASM: pisahkan aset target resmi dari tabrakan nama dan soft-404."""
    try:
        anchor = canonical_domain.strip().lower()
        if not anchor and settings.allowed_hosts_list:
            anchor = settings.allowed_hosts_list[0]

        if not anchor:
            return "Error: canonical_domain wajib diisi atau konfigurasikan ALLOWED_HOSTS."

        items = [line.strip() for line in re.split(r"[\n,]+", assets_raw) if line.strip()]
        if not items:
            return "Tidak ada aset yang diberikan untuk di-triage."

        in_scope = []
        quarantined = []
        soft_404_alerts = []

        anchor_parts = anchor.split(".")
        anchor_root = ".".join(anchor_parts[-2:]) if len(anchor_parts) >= 2 else anchor
        anchor_keyword = anchor_parts[0] if anchor_parts else anchor

        for item in items:
            host_only = item.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0].strip().lower()

            if any(p in item.lower() for p in [".env", ".git", "actuator", "phpinfo", "admin.php"]):
                soft_404_alerts.append(item)

            if host_only == anchor or host_only.endswith("." + anchor):
                in_scope.append(item)
            elif anchor_keyword in host_only:
                quarantined.append(f"{item} (Collision risk: mengandung kata kunci '{anchor_keyword}' tetapi bukan domain resmi)")
            else:
                quarantined.append(f"{item} (Third-party: domain berbeda total)")

        lines = [
            f"[Recon Scope Triage Report - Anchor: {anchor}]",
            f"Total Aset Dianalisis: {len(items)}",
            f"\n1. Aset Terverifikasi Milik Target (In-Scope: {len(in_scope)}):",
        ]
        if in_scope:
            for a in in_scope:
                lines.append(f"  [+] {_sanitize_untrusted(a)}")
        else:
            lines.append("  (Tidak ada aset yang lolos verifikasi kepemilikan langsung)")

        lines.append(f"\n2. Aset Dikarantina / Namespace Collisions (Quarantined: {len(quarantined)}):")
        if quarantined:
            for q in quarantined:
                lines.append(f"  [-] {_sanitize_untrusted(q)}")
        else:
            lines.append("  (Nol tabrakan nama)")

        if soft_404_alerts:
            lines.append("\n3. Peringatan Soft-404 Kontrol Wajib:")
            for s in soft_404_alerts:
                lines.append(
                    f"  [!] {_sanitize_untrusted(s)}: Verifikasi dengan junk-path (misal: /zzz-nonsense-$RANDOM) sebelum melaporkan temuan."
                )

        return "\n".join(lines)
    except Exception as e:
        return f"Error triage recon: {e}"

@mcp.tool()
async def zap_osint_fingerprint(target_url: str) -> str:
    """Fingerprint pasif teknologi target, server banner, dan deteksi WAF/CDN."""
    try:
        enforce_scope(target_url)
        async with httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=False) as client:
            resp = await client.get(target_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSINT-Recon"})
            headers = resp.headers

            server = headers.get("server", "Tidak terdeteksi")
            powered_by = headers.get("x-powered-by", "")
            via = headers.get("via", "")
            cf_ray = headers.get("cf-ray", "")
            aws_id = headers.get("x-amz-cf-id", "")

            tech = []
            if cf_ray:
                tech.append("Cloudflare CDN/WAF")
            if aws_id:
                tech.append("AWS CloudFront")
            if "nginx" in server.lower():
                tech.append("Nginx")
            if "apache" in server.lower():
                tech.append("Apache HTTPD")
            if "iis" in server.lower():
                tech.append("Microsoft IIS")
            if powered_by:
                tech.append(f"X-Powered-By: {powered_by}")
            if via:
                tech.append(f"Via: {via}")

            return (
                f"[OSINT Passive Fingerprint]\n"
                f"- Target URL: {_sanitize_untrusted(target_url)}\n"
                f"- Status Code: {resp.status_code}\n"
                f"- Server: {_sanitize_untrusted(server, 100)}\n"
                f"- Komponen Teridentifikasi: {', '.join(tech) if tech else 'Standar HTTP server'}\n"
                f"- Header Security Penting:\n"
                f"  * Strict-Transport-Security: {'Ada' if 'strict-transport-security' in headers else 'Tidak ada'}\n"
                f"  * Content-Security-Policy: {'Ada' if 'content-security-policy' in headers else 'Tidak ada'}\n"
                f"  * X-Frame-Options: {'Ada' if 'x-frame-options' in headers else 'Tidak ada'}\n"
                f"- Catatan Triage: Gunakan data ini untuk menyusun strategi pengujian tanpa probing agresif."
            )
    except ScopeViolation as e:
        return f"BLOCKED: {e.reason}"
    except Exception as e:
        return f"Error OSINT fingerprint: {e}"

if __name__ == "__main__":
    mcp.run()
