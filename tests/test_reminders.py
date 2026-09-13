import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage
from fastapi.testclient import TestClient

from backend.game import Action, Pet, act, evolve, present
from backend.reminders import ReminderRepository, reminder, send_reminders
from main import app

NOW = datetime(2026, 9, 12, tzinfo=UTC)


def recipient(**changes):
    pet = Pet(telegram_id=1, name="Луна", name_chosen=True, updated_at=NOW, **changes)
    return {
        "telegram_id": 1, "enabled": True, "last_care_at": None,
        "sleep_notified_at": None, "pet": pet.model_dump(mode="json"),
    }


def test_offline_needs_combined_and_cooldown():
    row = recipient()
    later = NOW + timedelta(hours=18)
    text, changes = reminder(row, later)
    assert all(word in text for word in ("Луна", "Покорми", "Поиграй", "Помой"))
    row.update(changes)
    assert reminder(row, later + timedelta(hours=5)) == ("", {})
    assert reminder(row, later + timedelta(hours=6))[1]


def test_healthy_unnamed_and_sleeping_pets_stay_quiet():
    assert reminder(recipient(), NOW) == ("", {})
    row = recipient(satiety=1)
    row["pet"]["name_chosen"] = False
    assert reminder(row, NOW) == ("", {})
    row = recipient(satiety=1, energy=40, sleep_started_at=NOW)
    assert reminder(row, NOW + timedelta(minutes=10)) == ("", {})


def test_full_energy_stays_full_until_woken_and_notifies_once():
    row = recipient(energy=94, sleep_started_at=NOW)
    later = NOW + timedelta(minutes=15)
    text, changes = reminder(row, later)
    assert "можешь меня разбудить" in text
    row.update(changes)
    assert reminder(row, later + timedelta(minutes=5)) == ("", {})
    pet = Pet.model_validate(row["pet"])
    assert present(pet, later)["can_wake"] is True
    awake = act(pet, Action.wake, later)
    assert awake.sleep_started_at is None
    assert awake.xp == pet.xp
    assert awake.energy == 100
    assert evolve(awake, later + timedelta(minutes=10)).energy < 100
    assert not present(awake, later)["can_wake"]
    assert reminder(row, NOW + timedelta(minutes=30)) == ("", {})


def test_new_sleep_can_notify_again():
    row = recipient(energy=94, sleep_started_at=NOW)
    row["sleep_notified_at"] = (NOW - timedelta(days=1)).isoformat()
    assert reminder(row, NOW + timedelta(minutes=15))[1]


def test_cron_requires_its_own_secret(monkeypatch):
    from backend.config import get_settings

    monkeypatch.setattr("main.get_settings", lambda: type("Settings", (), {"cron_secret": None})())
    with TestClient(app) as client:
        assert client.post("/api/cron/reminders").status_code == 403
    monkeypatch.setattr("main.get_settings", get_settings)


def test_claim_is_atomic_and_checks_enabled(monkeypatch):
    from types import SimpleNamespace

    from pydantic import SecretStr

    monkeypatch.setattr("backend.repository.get_settings", lambda: SimpleNamespace(
        supabase_url="https://example.com", supabase_service_role_key=SecretStr("test"),
    ))
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=[{}] if len(calls) == 1 else [])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            repo = ReminderRepository(client)
            row = recipient()
            changes = {"last_care_at": NOW.isoformat()}
            assert await repo.claim(row, changes)
            assert not await repo.claim(row, changes)

    asyncio.run(run())
    assert calls[0].url.params["last_care_at"] == "is.null"
    assert calls[0].url.params["enabled"] == "eq.true"


def test_delivery_claim_conflicts_and_telegram_failures():
    async def run():
        row = recipient(satiety=1)
        method = SendMessage(chat_id=1, text="test")
        for error in (
            None,
            TelegramForbiddenError(method=method, message="blocked"),
            TelegramNetworkError(method=method, message="timeout"),
            TelegramRetryAfter(method=method, message="wait", retry_after=60),
        ):
            repo = AsyncMock()
            repo.recipients.side_effect = [[row], []]
            repo.claim.return_value = True
            bot = AsyncMock()
            bot.send_message.side_effect = error
            result = await send_reminders(repo, bot, None)
            assert result["sent"] == (0 if error else 1)
            if isinstance(error, TelegramForbiddenError):
                repo.enable.assert_awaited_once_with(1, False)
            if isinstance(error, TelegramRetryAfter):
                assert result["rate_limited"] is True
                assert repo.claim.await_count == 2
        repo = AsyncMock()
        repo.recipients.side_effect = [[row], []]
        repo.claim.return_value = False
        bot = AsyncMock()
        await send_reminders(repo, bot, None)
        bot.send_message.assert_not_awaited()

    asyncio.run(run())
