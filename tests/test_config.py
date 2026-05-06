import pytest

from multi_agent_research_lab.core.config import Settings


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_CRITIC", raising=False)
    monkeypatch.delenv("CRITIC_QUALITY_THRESHOLD", raising=False)
    settings = Settings()
    assert settings.openai_model
    assert Settings.model_fields["enable_critic"].default is False
    assert Settings.model_fields["critic_quality_threshold"].default == 8.0
    assert settings.max_iterations >= 1
