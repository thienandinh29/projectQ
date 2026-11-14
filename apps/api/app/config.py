import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """App settings loaded from the repo-root .env, overridable by real env vars."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # .env is copied from .env.example with blank values; blank must mean "use the default".
        env_ignore_empty=True,
    )

    # Default points at the local Docker database from docker-compose.yml.
    database_url: str = "postgresql://postgres:postgres@localhost:54322/nodetrail"
    api_key: str = ""
    allow_unauthenticated_local_dev: bool = False
    demo_uploads_enabled: bool = False
    cors_origins: str = "http://localhost:3000"
    supabase_url: str = ""
    supabase_service_role_key: SecretStr = SecretStr("")
    upload_bucket: str = "uploads"
    embedding_backend: Literal["tei", "local"] = "local"
    # "bayes": posterior over knowledge states (default); "walk": the original graph walk.
    placement_strategy: Literal["bayes", "walk"] = "bayes"
    # Code practice (specs/code-sandbox): the runner service; routes are mounted only when set.
    runner_url: str = ""
    runner_token: SecretStr = SecretStr("")
    courses_dir: Path = REPO_ROOT / "data" / "courses"
    vocab_dir: Path = REPO_ROOT / "data" / "vocabulary"
    tei_url: str = "http://localhost:8080"
    tei_api_key: SecretStr = SecretStr("")
    search_provider: Literal["brave", "tavily"] = "brave"
    search_api_key: SecretStr = SecretStr("")
    google_cloud_project: str = ""
    vertex_location: str = "asia-southeast1"
    google_application_credentials: str = ""
    aws_region: str = "ap-southeast-1"
    aws_profile: str = ""
    openrouter_api_key: SecretStr = SecretStr("")
    deepseek_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    gemini_verify_model: str = ""
    deepseek_free_model: str = ""
    deepseek_pro_model: str = ""
    vertex_free_model: str = ""
    vertex_graph_model: str = ""
    vertex_verify_model: str = ""
    bedrock_free_model: str = ""
    bedrock_pro_model: str = ""
    bedrock_verify_model: str = ""
    openrouter_free_model: str = ""
    openrouter_graph_model: str = ""
    openrouter_pro_model: str = ""
    openrouter_verify_model: str = ""

    def export_worker_environment(self) -> None:
        """P3 reads process environment; forward supported settings without logging values."""
        for name in (
            "search_provider",
            "search_api_key",
            "google_cloud_project",
            "vertex_location",
            "google_application_credentials",
            "aws_region",
            "aws_profile",
            "openrouter_api_key",
            "deepseek_api_key",
            "gemini_api_key",
            "gemini_verify_model",
            "deepseek_free_model",
            "deepseek_pro_model",
            "vertex_free_model",
            "vertex_graph_model",
            "vertex_verify_model",
            "bedrock_free_model",
            "bedrock_pro_model",
            "bedrock_verify_model",
            "openrouter_free_model",
            "openrouter_graph_model",
            "openrouter_pro_model",
            "openrouter_verify_model",
        ):
            value = getattr(self, name)
            if isinstance(value, SecretStr):
                value = value.get_secret_value()
            if value:
                os.environ.setdefault(name.upper(), value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
