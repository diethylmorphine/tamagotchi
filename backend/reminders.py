"""Scheduled Telegram reminders with durable, conditional delivery claims."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

from backend.game import SLEEP_SECONDS, Pet, evolve, sleep_remaining
from backend.repository import PetRepository

logger = logging.getLogger(__name__)
PREFERENCE_KEYS = ("notify_hunger", "notify_mood", "notify_hygiene", "notify_sleep")
CARE_INTERVAL = timedelta(hours=6)


class ReminderRepository(PetRepository):
    def __init__(self, client):
        super().__init__(client)
        self.url = self.url.removesuffix("pets") + "pet_reminders"

    @property
    def scheduler_url(self):
        return self.url.removesuffix("pet_reminders") + "reminder_scheduler"

    async def start_run(self, now: datetime):
        await self.request(
            "POST", url=self.scheduler_url, params={"on_conflict": "id"},
            headers={"Prefer": "resolution=merge-duplicates"},
            json={"id": 1, "started_at": now.isoformat()},
        )

    async def finish_run(self, started: datetime, result: dict):
        await self.request(
            "PATCH", url=self.scheduler_url,
            params={"id": "eq.1", "started_at": f"eq.{started.isoformat()}"},
            json={"completed_at": datetime.now(UTC).isoformat(),
                  "sent": result["sent"], "failed": result["failed"]},
        )

    async def scheduler_status(self) -> dict:
        response = await self.request("GET", url=self.scheduler_url, params={
            "id": "eq.1", "select": "completed_at,failed", "limit": "1",
        })
        rows = response.json()
        completed = rows[0]["completed_at"] if rows else None
        recent = completed and (
            timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(completed)
            < timedelta(minutes=15)
        )
        return {
            "scheduler_healthy": bool(recent),
            "last_run_at": completed,
        }

    async def enable(self, user_id: int, enabled: bool):
        await self.request(
            "POST", params={"on_conflict": "telegram_id"},
            headers={"Prefer": "resolution=merge-duplicates"},
            json={"telegram_id": user_id, "enabled": enabled},
        )

    async def preferences(self, user_id: int) -> dict:
        response = await self.request("GET", params={
            "telegram_id": f"eq.{user_id}",
            "select": "enabled," + ",".join(PREFERENCE_KEYS), "limit": "1",
        })
        rows = response.json()
        return rows[0] if rows else {"enabled": False, **dict.fromkeys(PREFERENCE_KEYS, True)}

    async def update_preferences(self, user_id: int, changes: dict):
        await self.request(
            "POST", params={"on_conflict": "telegram_id"},
            headers={"Prefer": "resolution=ignore-duplicates"},
            json={"telegram_id": user_id, "enabled": False},
        )
        await self.request(
            "PATCH", params={"telegram_id": f"eq.{user_id}"}, json=changes,
        )

    async def is_enabled(self, user_id: int) -> bool:
        response = await self.request("GET", params={
            "telegram_id": f"eq.{user_id}", "select": "enabled", "limit": "1",
        })
        rows = response.json()
        return bool(rows and rows[0]["enabled"])

    async def recipients(self, after: int):
        response = await self.request("GET", params={
            "select": "*,pet:pets(*)", "enabled": "eq.true",
            "telegram_id": f"gt.{after}", "order": "telegram_id.asc", "limit": "100",
        })
        return response.json()

    async def claim(self, row: dict, changes: dict) -> bool:
        params = {"telegram_id": f"eq.{row['telegram_id']}", "enabled": "eq.true"}
        for key in PREFERENCE_KEYS:
            if key in row:
                params[key] = "eq.true" if row[key] else "eq.false"
        for key in changes:
            params[key] = f"eq.{row[key]}" if row[key] else "is.null"
        response = await self.request(
            "PATCH", params=params, headers={"Prefer": "return=representation"}, json=changes,
        )
        return bool(response.json())


def reminder(row: dict, now: datetime) -> tuple[str, dict]:
    pet = evolve(Pet.model_validate(row["pet"]), now)
    if not pet.name_chosen:
        return "", {}
    # A cron tick can fall just after the final sleep reward. Do not lose that
    # notification merely because the pet has already automatically woken up.
    if pet.sleep_started_at and row.get("notify_sleep", True):
        end = pet.sleep_started_at + timedelta(seconds=SLEEP_SECONDS)
        notified = row["sleep_notified_at"]
        already_notified = (
            notified and datetime.fromisoformat(notified) == pet.sleep_started_at
        )
        interacted = pet.last_action_at and pet.last_action_at > pet.sleep_started_at
        if end <= now < end + timedelta(hours=1) and not already_notified and not interacted:
            return (
                f"☀️ {pet.name}: сон закончился! Я снова готов играть.",
                {"sleep_notified_at": pet.sleep_started_at.isoformat()},
            )
    if sleep_remaining(pet, now) > 0:
        start = pet.sleep_started_at.isoformat()
        notified = row["sleep_notified_at"]
        if row.get("notify_sleep", True) and pet.energy >= 100 and (
            not notified or datetime.fromisoformat(notified) != pet.sleep_started_at
        ):
            return (
                f"☀️ {pet.name}: энергия полная! Я уже выспался — можешь меня разбудить.",
                {"sleep_notified_at": start},
            )
        return "", {}
    last_care = row["last_care_at"]
    if last_care and now - datetime.fromisoformat(last_care) < CARE_INTERVAL:
        return "", {}
    needs = []
    for stat, preference, text in (
        ("satiety", "notify_hunger", "🍎 Покорми меня — я проголодался."),
        ("happiness", "notify_mood", "🎾 Поиграй со мной — мне скучно."),
        ("hygiene", "notify_hygiene", "🛁 Помой меня — пора купаться."),
    ):
        if row.get(preference, True) and getattr(pet, stat) < 30:
            needs.append(text)
    if not needs:
        return "", {}
    return f"🐾 {pet.name} зовёт тебя!\n\n" + "\n".join(needs), {
        "last_care_at": now.isoformat(),
    }


async def send_reminders(repo: ReminderRepository, bot: Bot, keyboard) -> dict:
    sent = 0
    failed = 0
    after = 0
    while rows := await repo.recipients(after):
        for row in rows:
            after = row["telegram_id"]
            text, changes = reminder(row, datetime.now(UTC))
            if not changes or not await repo.claim(row, changes):
                continue
            try:
                await bot.send_message(after, text, reply_markup=keyboard)
                sent += 1
            except TelegramForbiddenError:
                await repo.enable(after, False)
                failed += 1
            except TelegramRetryAfter:
                await repo.claim({**row, **changes}, {key: row[key] for key in changes})
                return {"sent": sent, "failed": failed + 1, "rate_limited": True}
            except TelegramAPIError:
                # Delivery may have succeeded despite a network error. Keep the claim
                # to avoid duplicates; a later care window / new sleep can notify again.
                logger.warning("Telegram reminder delivery failed for %s", after)
                failed += 1
            await asyncio.sleep(0.05)
    return {"sent": sent, "failed": failed}
