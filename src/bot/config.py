"""Typed settings loaded from env / .env."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    anthropic_api_key: str
    vault_path: Path
    index_path: Path = Path("data/index.db")
    vault_search_db_path: Path = Path("data/vault_search.db")
    scheduler_state_path: Path = Path("data/scheduler_state.json")
    memory_db_path: Path = Path("data/memory.db")
    model: str = "claude-opus-4-8"
    max_tokens: int = 8192
