from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.config import Settings


class RAGSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Settings.model_config.get("env_file"), extra="ignore"
    )

    rag_chunk_tokens: int = Field(default=800, ge=4, le=8191)
    rag_chunk_overlap_tokens: int = Field(default=100, ge=0)
    rag_top_k: int = Field(default=5, ge=1)

    @model_validator(mode="after")
    def check_overlap(self) -> RAGSettings:
        if self.rag_chunk_overlap_tokens >= self.rag_chunk_tokens:
            raise ValueError("RAG overlap must be smaller than chunk size")
        return self
