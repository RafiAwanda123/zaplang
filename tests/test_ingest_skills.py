from pathlib import Path
from scripts.ingest_skills import resolve_category, collect_skill_files, prepare_documents

def test_resolve_category():
    assert resolve_category("xss-payloads") == "xss"
    assert resolve_category("sqli-attacks") == "sqli"
    assert resolve_category("idor-methodology") == "idor"
    assert resolve_category("bugcrowd-reporting") == "general"

def test_prepare_documents_chunks_oversized(tmp_path: Path):
    dummy_file = tmp_path / "SKILL.md"
    dummy_file.write_text("A" * 1500, encoding="utf-8")

    entries = [("test-skill", dummy_file)]
    docs = prepare_documents(entries, max_bytes=1000)

    assert len(docs) > 1
    assert docs[0].trust == "curated"
    assert "part1" in docs[0].source

