from typing import Literal
from pydantic import BaseModel, Field

class DocumentIn(BaseModel):
    title: str = Field(default="", description="Judul dokumen")
    source: str = Field(default="unknown", description="Sumber dokumen")
    content: str = Field(..., description="Isi teks")
    category: Literal["xss", "idor", "sqli", "general"] = "general"
    trust: Literal["curated", "unverified"] = "unverified"

DocumentIngest = DocumentIn

class QueryIn(BaseModel):
    query: str
    top_k: int = Field(default=4, ge=1, le=20)
    category: str | None = None
    include_unverified: bool = False

class QueryRequest(BaseModel):
    query: str | None = None
    question: str | None = None
    top_k: int = Field(default=4, ge=1, le=20)
    category: str | None = None

    def get_query_text(self) -> str:
        return (self.query or self.question or "").strip()

class ChunkResult(BaseModel):
    content: str
    source: str
    category: str
    score: float

class QueryResultItem(BaseModel):
    content: str
    source: str
    category: str
    score: float

class QueryResponse(BaseModel):
    answer: str = ""
    sources: list[str] = Field(default_factory=list)
    results: list[QueryResultItem] = Field(default_factory=list)
