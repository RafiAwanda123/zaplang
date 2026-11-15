from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    zap_base: str = "http://127.0.0.1:8080"
    zap_api_key: str
    allowed_hosts: str = ""
    database_url: str
    ollama_url: str = "http://localhost:11434"
    embed_model: str = "nomic-embed-text"
    rag_api_key: str = ""
    rag_max_doc_bytes: int = 200_000
    rag_score_threshold: float = 0.25
    rag_top_k: int = 4
    openrouter_api_key: str = ""
    openrouter_model: str = "nvidia/nemotron-3.5-lightning:free"
    log_level: str = "INFO"

    @field_validator("zap_api_key", mode="before")
    @classmethod
    def _require_zap_api_key(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ZAP_API_KEY wajib diisi di .env.")
        return v

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip().lower() for h in self.allowed_hosts.split(",") if h.strip()]

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

settings: Settings = get_settings()
