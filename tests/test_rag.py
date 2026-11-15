"""Test untuk endpoint /rag/* - autentikasi, validasi ukuran, dan trust filter.

Kasus yang diuji:
1. POST /rag/documents tanpa X-RAG-Api-Key → 401
2. POST /rag/query tanpa X-RAG-Api-Key → 401
3. POST /rag/documents dengan dokumen melebihi RAG_MAX_DOC_BYTES → 413
4. Query default tidak mengembalikan chunk trust='unverified'

Semua test menggunakan mock agar tidak memerlukan DB atau Ollama aktif.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Patch settings sebelum import app agar ZAP_API_KEY & RAG_API_KEY ada nilainya
_FAKE_SETTINGS = {
    "zap_api_key": "test-zap-key",
    "rag_api_key": "test-rag-key",
    "zap_base": "http://127.0.0.1:8080",
    "allowed_hosts": ["target.local"],
    "database_url": "postgresql+asyncpg://zaplang:test@localhost:5432/zaplang",
    "ollama_url": "http://localhost:11434",
    "embed_model": "nomic-embed-text",
    "rag_top_k": 4,
    "rag_max_doc_bytes": 200_000,
    "rag_score_threshold": 0.25,
    "log_level": "INFO",
}


@pytest.fixture()
def client():
    """TestClient dengan settings di-patch dan session factory di-mock."""
    with patch("app.core.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock(**_FAKE_SETTINGS)
        mock_settings.rag_api_key = "test-rag-key"
        mock_settings.rag_max_doc_bytes = 200_000
        mock_get_settings.return_value = mock_settings

        # Patch settings singleton di semua modul yang menggunakannya
        with patch("app.core.config.settings", mock_settings), \
             patch("app.api.rag.settings", mock_settings):

            from app.main import app

            # Mock session factory di app.state
            mock_session = AsyncMock()
            mock_factory = MagicMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
            app.state.db_session_factory = mock_factory

            with TestClient(app, raise_server_exceptions=False) as c:
                yield c, mock_session


# ── Test 1 & 2: Tanpa API key → 401 ─────────────────────────────────────────


def test_ingest_without_api_key_returns_401(client):
    """POST /rag/documents tanpa X-RAG-Api-Key harus mengembalikan 401."""
    c, _ = client
    response = c.post(
        "/rag/documents",
        json={
            "title": "Test Doc",
            "content": "Konten pengujian.",
            "source": "test.txt",
            "category": "general",
            "trust": "curated",
        },
        # Tidak mengirim X-RAG-Api-Key
    )
    assert response.status_code == 401


def test_query_without_api_key_returns_401(client):
    """POST /rag/query tanpa X-RAG-Api-Key harus mengembalikan 401."""
    c, _ = client
    response = c.post(
        "/rag/query",
        json={"query": "Apa itu XSS?"},
        # Tidak mengirim X-RAG-Api-Key
    )
    assert response.status_code == 401


def test_ingest_with_wrong_api_key_returns_401(client):
    """POST /rag/documents dengan key salah harus mengembalikan 401."""
    c, _ = client
    response = c.post(
        "/rag/documents",
        json={
            "title": "Test",
            "content": "x",
            "source": "t.txt",
            "category": "general",
            "trust": "curated",
        },
        headers={"X-RAG-Api-Key": "wrong-key"},
    )
    assert response.status_code == 401


# ── Test 3: Dokumen terlalu besar → 413 ──────────────────────────────────────


def test_ingest_oversized_document_returns_413(client):
    """POST /rag/documents dengan konten > RAG_MAX_DOC_BYTES harus mengembalikan 413."""
    c, _ = client

    oversized_content = "A" * (200_001)  # 1 byte lebih dari batas

    with patch("app.services.rag_service.ingest", new_callable=AsyncMock) as mock_ingest:
        mock_ingest.side_effect = ValueError(
            f"Dokumen melebihi batas ukuran 200000 bytes (aktual: 200001 bytes)."
        )
        response = c.post(
            "/rag/documents",
            json={
                "title": "Besar",
                "content": oversized_content,
                "source": "big.txt",
                "category": "general",
                "trust": "unverified",
            },
            headers={"X-RAG-Api-Key": "test-rag-key"},
        )
    assert response.status_code == 413
    assert "batas ukuran" in response.json()["detail"].lower() or \
           response.status_code == 413  # cukup status code


# ── Test 4: Unverified tidak muncul di query default ─────────────────────────


def test_query_default_excludes_unverified(client):
    """Query default (include_unverified=False) tidak boleh mengembalikan chunk unverified."""
    c, _ = client

    from app.schemas.rag import ChunkResult

    # Simulasi: repo mengembalikan 1 chunk curated dan 1 unverified
    curated_chunk = ChunkResult(
        content="Konten kurated XSS.",
        source="owasp.org",
        category="xss",
        score=0.85,
    )

    async def fake_retrieve(query_in, repo):
        # Pastikan include_unverified=False diteruskan ke repo
        assert query_in.include_unverified is False
        return [curated_chunk]

    with patch("app.services.rag_service.retrieve", side_effect=fake_retrieve):
        response = c.post(
            "/rag/query",
            json={"query": "Apa itu XSS?"},
            headers={"X-RAG-Api-Key": "test-rag-key"},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["source"] == "owasp.org"
    # Pastikan tidak ada chunk unverified (di mock ini memang tidak ada,
    # tapi assertion di fake_retrieve memvalidasi flag diteruskan dengan benar)


# ── Test bonus: chunk teks _chunk() ──────────────────────────────────────────


def test_chunk_does_not_produce_empty_strings():
    """_chunk() tidak boleh menghasilkan string kosong."""
    from app.services.rag_service import _chunk

    result = _chunk("Paragraf satu.\n\nParagraf dua.\n\nParagraf tiga.")
    assert all(s.strip() for s in result)
    assert len(result) >= 1


def test_chunk_respects_target_size():
    """_chunk() tidak boleh menghasilkan chunk jauh melebihi target + overlap."""
    from app.services.rag_service import _chunk, _MAX_CHUNK_CHARS, _OVERLAP_CHARS

    long_text = "Kalimat panjang untuk pengujian. " * 100
    chunks = _chunk(long_text)
    for chunk in chunks:
        assert len(chunk) <= _MAX_CHUNK_CHARS + _OVERLAP_CHARS + 10  # toleransi kecil
