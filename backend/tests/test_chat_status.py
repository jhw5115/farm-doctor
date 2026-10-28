from app.chat import chat_status
from app.config import settings


def test_chat_status_waits_without_external_ai(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "chat_model", "")

    status = chat_status()

    assert status["available"] is False
    assert status["mode"] == "waiting_for_configuration"
    assert status["inspection_lookup_enabled"] is False


def test_chat_status_is_ready_only_with_server_side_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "server-only-key")
    monkeypatch.setattr(settings, "chat_model", "configured-model")

    status = chat_status()

    assert status["available"] is True
    assert status["mode"] == "ready"
