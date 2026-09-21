import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.telegram_setup import configure_telegram
from main import app


def settings():
    return SimpleNamespace(
        webapp_url="https://example.com/", webhook_secret=SecretStr("w" * 32),
        cron_secret=SecretStr("c" * 32), bot_token=SecretStr("99:" + "a" * 35),
    )


def test_setup_accepts_menu_callbacks_and_preserves_pending_commands():
    bot = AsyncMock()
    asyncio.run(configure_telegram(bot, settings()))
    bot.set_webhook.assert_awaited_once_with(
        url="https://example.com/api/telegram/webhook", secret_token="w" * 32,
        allowed_updates=["message", "callback_query"], drop_pending_updates=False,
    )
    bot.set_chat_menu_button.assert_awaited_once()


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_remote_setup_requires_cron_secret(monkeypatch, method):
    monkeypatch.setattr("main.get_settings", settings)
    factory = AsyncMock()
    monkeypatch.setattr("main.Bot", factory)
    with TestClient(app) as client:
        for authorization in ("", "Bearer incorrect", "tma anything"):
            response = client.request(method, "/api/cron/telegram", headers={
                "Authorization": authorization,
            })
            assert response.status_code == 403
    factory.assert_not_called()


def test_remote_status_is_read_only_and_repair_uses_server_credentials(monkeypatch):
    monkeypatch.setattr("main.get_settings", settings)
    bot = AsyncMock()
    bot.get_webhook_info.return_value = SimpleNamespace(
        url="https://example.com/api/telegram/webhook",
        allowed_updates=["message", "callback_query"],
        pending_update_count=2, last_error_date=None, last_error_message=None,
    )
    context = AsyncMock()
    context.__aenter__.return_value = bot
    monkeypatch.setattr("main.Bot", lambda **kwargs: context)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + "c" * 32}
        status = client.get("/api/cron/telegram", headers=headers)
        assert status.status_code == 200
        assert status.json()["pending_updates"] == 2
        bot.set_webhook.assert_not_awaited()
        response = client.post("/api/cron/telegram", headers=headers)
        assert response.status_code == 200
        assert response.json()["webhook_matches_app"]
        assert "w" * 32 not in response.text
        assert "a" * 35 not in response.text
        bot.set_webhook.assert_awaited_once()
