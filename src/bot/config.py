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
    socket_path: Path = Path.home() / ".sipa" / "sipa.sock"  # fixed abs path; cwd-independent
    timer_interval: float = 60.0  # seconds between wall-clock scheduler checks
    provider: str = "anthropic"  # "anthropic" | "local" (local is a scaffold, not wired yet)
    model: str = "claude-opus-4-8"
    max_tokens: int = 8192
    input_price_per_mtok: float = 5.0  # claude-opus-4-8 pricing; set to your plan/model rate
    output_price_per_mtok: float = 25.0
