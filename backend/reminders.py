"""Scheduled Telegram reminders with durable, conditional delivery claims."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

from backend.game import Pet, evolve, sleep_remaining
from backend.repository import PetRepository

logger = logging.getLogger(__name__)
CARE_INTERVAL = timedelta(hours=6)


class ReminderRepository(PetRepository):
    def __init__(self, client):
        super().__init__(client)
        self.url = self.url.removesuffix("pets") + "pet_reminders"

    async def enable(self, user_id: int, enabled: bool):
        await self.request(
            "POST", params={"on_conflict": "telegram_id"},
            headers={"Prefer": "resolution=merge-duplicates"},
            json={"telegram_id": user_id, "enabled": enabled},
        )

    async def recipients(self, after: int):
        response = await self.request("GET", params={
            "select": "*,pet:pets(*)", "enabled": "eq.true",
            "telegram_id": f"gt.{after}", "order": "telegram_id.asc", "limit": "100",
        })
        return response.json()

    async def claim(self, row: dict, changes: dict) -> bool:
        params = {"telegram_id": f"eq.{row['telegram_id']}", "enabled": "eq.true"}
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
    if sleep_remaining(pet, now) > 0:
        start = pet.sleep_started_at.isoformat()
        notified = row["sleep_notified_at"]
        if pet.energy >= 100 and (
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
    for stat, text in (
        ("satiety", "🍎 Покорми меня — я проголодался."),
        ("happiness", "🎾 Поиграй со мной — мне скучно."),
        ("hygiene", "🛁 Помой меня — пора купаться."),
    ):
        if getattr(pet, stat) < 30:
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
