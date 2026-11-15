import uuid
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

class KnowledgeRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_chunk(
        self,
        *,
        doc_id: uuid.UUID,
        content: str,
        embedding: list[float],
        source: str,
        category: str,
        trust: str,
    ) -> uuid.UUID:
        chunk_id = uuid.uuid4()
        stmt = text(
            """
            INSERT INTO knowledge_chunks (id, doc_id, content, embedding, source, category, trust)
            VALUES (:id, :doc_id, :content, CAST(:embedding AS vector), :source, :category, :trust)
            """
        )
        await self._session.execute(
            stmt,
            {
                "id": str(chunk_id),
                "doc_id": str(doc_id),
                "content": content,
                "embedding": str(embedding),
                "source": source,
                "category": category,
                "trust": trust,
            },
        )
        await self._session.commit()
        return chunk_id

    async def cosine_search(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        category: str | None = None,
        include_unverified: bool = False,
    ) -> list[dict[str, Any]]:
        trust_filter = "" if include_unverified else "AND trust = 'curated'"
        category_filter = "AND category = :category" if category is not None else ""

        stmt = text(
            f"""
            SELECT id, content, source, category, trust,
                   1 - (embedding <=> CAST(:query_embedding AS vector)) AS score
            FROM knowledge_chunks
            WHERE 1=1 {trust_filter} {category_filter}
            ORDER BY embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k
            """
        )

        params: dict[str, Any] = {"query_embedding": str(query_embedding), "top_k": top_k}
        if category is not None:
            params["category"] = category

        result = await self._session.execute(stmt, params)
        return [dict(row) for row in result.mappings().all()]
