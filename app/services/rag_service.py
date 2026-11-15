import re
from unittest.mock import AsyncMock, patch
import httpx
from app.core.config import settings
from app.core.scope import enforce_scope
from app.repositories.knowledge_repo import KnowledgeRepo
from app.schemas.rag import DocumentIn, QueryIn, QueryResultItem, QueryResponse, ChunkResult

_TARGET_CHUNK_CHARS = 800
_MAX_CHUNK_CHARS = 800
_OVERLAP_CHARS = 80
_OLLAMA_TIMEOUT = 30.0
_SPLIT_REGEX = re.compile(r"(?:(?:^|\n)#{1,6}\s+.+|\n{2,})")
_SENTENCE_REGEX = re.compile(r"(?<=[.!?])\s+")

def _chunk(text: str) -> list[str]:
    raw_segments = [s.strip() for s in _SPLIT_REGEX.split(text) if s.strip()]
    chunks = []
    buffer = ""
    prev_tail = ""
    max_len = _TARGET_CHUNK_CHARS + _OVERLAP_CHARS

    for seg in raw_segments:
        sentences = _SENTENCE_REGEX.split(seg) if len(seg) > _TARGET_CHUNK_CHARS else [seg]
        for sent in sentences:
            if len(buffer) + len(sent) + 1 <= _TARGET_CHUNK_CHARS:
                buffer = f"{buffer} {sent}".strip() if buffer else sent
            else:
                if buffer:
                    chunks.append((prev_tail + buffer)[:max_len])
                    prev_tail = buffer[-_OVERLAP_CHARS:] if len(buffer) > _OVERLAP_CHARS else buffer
                buffer = sent

    if buffer:
        chunks.append((prev_tail + buffer)[:max_len])

    return [c for c in chunks if c.strip()]

async def _embed(texts: list[str]) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/embed",
            json={"model": settings.embed_model, "input": texts},
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]

async def ingest(doc: DocumentIn, repo: KnowledgeRepo) -> dict:
    content_bytes = doc.content.encode("utf-8")
    if len(content_bytes) > settings.rag_max_doc_bytes:
        raise ValueError(
            f"Dokumen melebihi batas ukuran {settings.rag_max_doc_bytes} bytes "
            f"(aktual: {len(content_bytes)} bytes)."
        )

    chunks = _chunk(doc.content)
    if not chunks:
        return {"doc_id": None, "chunks_saved": 0}

    embeddings = await _embed(chunks)
    import uuid
    doc_id = uuid.uuid4()

    for chunk_text, embedding in zip(chunks, embeddings, strict=True):
        await repo.insert_chunk(
            doc_id=doc_id,
            content=chunk_text,
            embedding=embedding,
            source=doc.source,
            category=doc.category,
            trust=doc.trust,
        )

    return {"doc_id": str(doc_id), "chunks_saved": len(chunks)}

async def retrieve(query_in: QueryIn, repo: KnowledgeRepo) -> list[ChunkResult]:
    embeddings = await _embed([query_in.query])
    rows = await repo.cosine_search(
        query_embedding=embeddings[0],
        top_k=query_in.top_k,
        category=query_in.category,
        include_unverified=query_in.include_unverified,
    )

    results = []
    for row in rows:
        score = round(float(row.get("score", 0.0)), 4)
        if score < settings.rag_score_threshold:
            continue
        results.append(
            ChunkResult(
                content=str(row["content"]),
                source=str(row["source"]),
                category=str(row["category"]),
                score=score,
            )
        )
    return results
