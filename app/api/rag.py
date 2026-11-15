from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import get_db
from app.repositories.knowledge_repo import KnowledgeRepo
from app.schemas.rag import DocumentIn, QueryIn, QueryRequest, QueryResponse, QueryResultItem
from app.services import rag_service

router = APIRouter(tags=["rag"])

def _require_rag_key(x_rag_api_key: str | None = Header(default=None, alias="X-RAG-Api-Key")) -> None:
    if not x_rag_api_key or x_rag_api_key != settings.rag_api_key:
        raise HTTPException(status_code=401, detail="X-RAG-Api-Key missing or invalid")

@router.post("/documents", status_code=201, dependencies=[Depends(_require_rag_key)])
async def ingest_documents(payload: DocumentIn, db: AsyncSession = Depends(get_db)) -> dict:
    repo = KnowledgeRepo(db)
    try:
        return await rag_service.ingest(payload, repo)
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))

@router.post("/query", response_model=QueryResponse, dependencies=[Depends(_require_rag_key)])
async def query_documents(payload: QueryRequest, db: AsyncSession = Depends(get_db)) -> QueryResponse:
    query_text = payload.get_query_text()
    if not query_text:
        raise HTTPException(status_code=422, detail="Field 'query' atau 'question' wajib diisi.")

    repo = KnowledgeRepo(db)
    query_in = QueryIn(
        query=query_text,
        top_k=payload.top_k,
        category=payload.category,
        include_unverified=False,
    )
    chunks = await rag_service.retrieve(query_in, repo)
    sources = list({c.source for c in chunks})
    items = [
        QueryResultItem(content=c.content, source=c.source, category=c.category, score=c.score)
        for c in chunks
    ]
    answer = "\n\n".join(c.content for c in chunks) if chunks else "Tidak ada dokumen relevan."
    return QueryResponse(answer=answer, sources=sources, results=items)
