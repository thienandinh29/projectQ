import pytest
from pydantic import ValidationError

from app.config import Settings


def test_blank_env_value_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    settings = Settings(_env_file=None)
    assert settings.database_url.endswith("localhost:54322/nodetrail")


def test_env_value_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@example:5432/db")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql://u:p@example:5432/db"


def test_embedding_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.rag.embed import TeiEmbedder, make_embedder

    monkeypatch.setenv("EMBEDDING_BACKEND", "tei")
    monkeypatch.setenv("TEI_URL", "http://localhost:18080")
    monkeypatch.setenv("TEI_API_KEY", "test-embedding-key")
    settings = Settings(_env_file=None)
    assert settings.embedding_backend == "tei"
    assert settings.tei_url == "http://localhost:18080"
    assert settings.tei_api_key.get_secret_value() == "test-embedding-key"
    assert "test-embedding-key" not in repr(settings)
    embedder = make_embedder(
        settings.embedding_backend,
        tei_url=settings.tei_url,
        api_key=settings.tei_api_key.get_secret_value() or None,
    )
    assert isinstance(embedder, TeiEmbedder)


def test_embedding_settings_default_and_invalid_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("EMBEDDING_BACKEND", "TEI_URL", "TEI_API_KEY"):
        monkeypatch.setenv(name, "")
    settings = Settings(_env_file=None)
    assert settings.embedding_backend == "local"
    assert settings.tei_url == "http://localhost:8080"
    assert not settings.tei_api_key.get_secret_value()
    monkeypatch.setenv("EMBEDDING_BACKEND", "managed")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_worker_environment_forwarding(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    from pydantic import SecretStr

    for name in ("SEARCH_API_KEY", "VERTEX_GRAPH_MODEL", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VERTEX_LOCATION", "shell-location")
    settings = Settings(
        _env_file=None,
        search_api_key=SecretStr("private-search"),
        openrouter_api_key=SecretStr("private-provider"),
        vertex_graph_model="gemini-test",
        vertex_location="settings-location",
    )
    settings.export_worker_environment()
    assert os.environ["SEARCH_API_KEY"] == "private-search"
    assert os.environ["OPENROUTER_API_KEY"] == "private-provider"
    assert os.environ["VERTEX_GRAPH_MODEL"] == "gemini-test"
    assert os.environ["VERTEX_LOCATION"] == "shell-location"
    assert "private-search" not in repr(settings)
    assert "private-provider" not in repr(settings)


def test_deepseek_settings_forwarding_and_secret_masking(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_FREE_MODEL", "DEEPSEEK_PRO_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-deepseek-test")
    monkeypatch.setenv("DEEPSEEK_FREE_MODEL", "deepseek-flash")
    monkeypatch.setenv("DEEPSEEK_PRO_MODEL", "deepseek-v4-pro")
    settings = Settings(_env_file=None)
    assert "secret-deepseek-test" not in repr(settings)
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    monkeypatch.delenv("DEEPSEEK_FREE_MODEL")
    monkeypatch.delenv("DEEPSEEK_PRO_MODEL")
    settings.export_worker_environment()
    assert os.environ["DEEPSEEK_API_KEY"] == "secret-deepseek-test"
    assert os.environ["DEEPSEEK_FREE_MODEL"] == "deepseek-flash"
    assert os.environ["DEEPSEEK_PRO_MODEL"] == "deepseek-v4-pro"


def test_gemini_secret_export_and_shell_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    monkeypatch.setenv("GEMINI_API_KEY", "private-gemini-test")
    monkeypatch.setenv("GEMINI_VERIFY_MODEL", "gemini-test")
    settings = Settings(_env_file=None)
    assert "private-gemini-test" not in repr(settings)
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("GEMINI_VERIFY_MODEL", "gemini-shell-test")
    settings.export_worker_environment()
    assert os.environ["GEMINI_API_KEY"] == "private-gemini-test"
    assert os.environ["GEMINI_VERIFY_MODEL"] == "gemini-shell-test"
