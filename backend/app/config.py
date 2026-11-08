"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All runtime configuration. Values come from env vars or a local .env file."""

    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", ".env"), extra="ignore", env_ignore_empty=True)

    dev_auth_bypass: bool = False
    database_url: str = "sqlite:///./dbcompass.db"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"
    knowledge_base_dir: Path = REPO_ROOT / "knowledge_base"

    entra_tenant_id: str = ""
    entra_api_client_id: str = ""

    gcp_billing_api_key: str = ""
    gcp_service_account_file: str = ""
    inr_per_usd: float | None = None
    inr_rate_date: str = ""

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        """Return CORS origins as a list, split from the comma-separated env value."""
        origins = []
        for origin in self.cors_origins.split(","):
            stripped_origin = origin.strip()
            if stripped_origin:
                origins.append(stripped_origin)
        return origins

    @property
    def entra_configured(self) -> bool:
        """True when enough Entra ID settings exist to validate tokens."""
        return bool(self.entra_tenant_id and self.entra_api_client_id)


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
