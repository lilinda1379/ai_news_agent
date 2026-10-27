from app.config import AppConfig


def test_config_reads_openai_and_storage_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "agent.db"))
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "workspace"))
    monkeypatch.setenv("APP_TIMEZONE", "Asia/Shanghai")

    config = AppConfig.from_env()

    assert config.openai_api_key == "test-key"
    assert config.openai_base_url == "https://llm.example/v1"
    assert config.openai_model == "test-model"
    assert config.database_path == tmp_path / "agent.db"
    assert config.workspace_root == tmp_path / "workspace"


def test_agent_max_steps_defaults_and_can_be_overridden(monkeypatch):
    monkeypatch.delenv("AGENT_MAX_STEPS", raising=False)
    assert AppConfig.from_env().agent_max_steps == 10

    monkeypatch.setenv("AGENT_MAX_STEPS", "3")
    assert AppConfig.from_env().agent_max_steps == 3

    monkeypatch.setenv("AGENT_MAX_STEPS", "not-a-number")
    assert AppConfig.from_env().agent_max_steps == 10
