"""LangChain tools untuk agen zaplang.

RENCANA IMPLEMENTASI (belum diisi):

Setiap tool = satu fungsi bertipe, sesuai aturan zap-api-tools:
- spider_start_tool(target_url: str) -> str
    Memanggil ZapClient.spider_start(). enforce_scope() sudah ada di dalam client.
    Tidak boleh memanggil ZAP langsung dari sini.

- get_alerts_tool(base_url: str, count: int) -> str
    Memanggil ZapClient.alerts().
    Hasil WAJIB melalui sanitasi untrusted-output-handling sebelum dikembalikan
    ke agen: truncate 200 karakter, bungkus <untrusted_data>, dedup.

- active_scan_tool(target_url: str, human_approved: bool) -> str
    Aksi berisiko; butuh human_approved=True.
    LLM tidak boleh mengisi human_approved - harus dari manusia (scope-guardrails rule #6).

Semua tool mendaftarkan diri ke ToolRegistry, bukan langsung ke agen,
supaya mudah di-test secara terisolasi.

Referensi:
- .agents/skills/zap-api-tools/SKILL.md
- .agents/skills/scope-guardrails/SKILL.md
- .agents/skills/untrusted-output-handling/SKILL.md
"""

