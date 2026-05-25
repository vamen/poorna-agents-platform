import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Force-load .env so our keys override any empty vars injected by the parent
# process (e.g. Claude Desktop sets ANTHROPIC_API_KEY="" which pydantic-settings
# would otherwise respect because env-vars take priority over .env files).
_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path, override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_env_path), env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./app.db"
    better_auth_url: str = "http://localhost:3000"
    better_auth_secret: str = "changeme"
    jwt_secret: str = "changeme"
    environment: str = "development"

    # ── Frontend origin (for OAuth redirect back to UI) ──────────────────────
    frontend_url: str = "http://localhost:5173"

    # ── Google OAuth (platform-owned app — Option A) ─────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""

    # ── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""

    # ── Temporal ─────────────────────────────────────────────────────────────
    temporal_host: str = "localhost:7233"


settings = Settings()
