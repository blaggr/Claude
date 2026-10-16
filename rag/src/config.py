from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    api_bearer_token: str = Field(default="", validation_alias="API_BEARER_TOKEN")

    chat_model: str = Field(default="gpt-4o", validation_alias="CHAT_MODEL")
    embedding_model: str = Field(default="text-embedding-3-large", validation_alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(default=3072, validation_alias="EMBEDDING_DIM")

    data_dir: Path = Field(default=Path("/var/data"), validation_alias="DATA_DIR")

    seed_domains: List[str] = Field(default_factory=lambda: ["qic-wa.org", "qic-wd.org"])
    seed_urls: List[str] = Field(
        default_factory=lambda: ["https://www.qic-wa.org", "https://qic-wd.org"]
    )

    max_pages_per_domain: int = Field(default=2000, validation_alias="MAX_PAGES_PER_DOMAIN")
    request_timeout_s: int = Field(default=30, validation_alias="REQUEST_TIMEOUT_S")
    crawl_concurrency: int = Field(default=8, validation_alias="CRAWL_CONCURRENCY")
    user_agent: str = Field(
        default="QIC-RAG-Crawler/1.0 (+research-bot; contact via site)",
        validation_alias="USER_AGENT",
    )

    chunk_tokens: int = Field(default=600, validation_alias="CHUNK_TOKENS")
    chunk_overlap: int = Field(default=80, validation_alias="CHUNK_OVERLAP")

    retrieval_k: int = Field(default=12, validation_alias="RETRIEVAL_K")
    retrieval_fetch_k: int = Field(default=40, validation_alias="RETRIEVAL_FETCH_K")

    reindex_cron: str = Field(default="0 7 * * 1", validation_alias="REINDEX_CRON")
    enable_scheduler: bool = Field(default=True, validation_alias="ENABLE_SCHEDULER")

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def state_file(self) -> Path:
        return self.data_dir / "state.json"


settings = Settings()
