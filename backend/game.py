"""Pure game rules. Only the server decides time, stats and rewards."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Action(StrEnum):
    feed = "feed"
    play = "play"
    wash = "wash"
    rest = "rest"
    wake = "wake"


class Pet(BaseModel):
    telegram_id: int
    owner_name: str | None = None
    owner_username: str | None = None
    name: str = "Питомец"
    name_chosen: bool = False
    species: Literal["cat", "fox", "snow_leopard", "snake"] = "cat"
    satiety: float = Field(default=80, ge=0, le=100)
    happiness: float = Field(default=80, ge=0, le=100)
    energy: float = Field(default=80, ge=0, le=100)
    hygiene: float = Field(default=80, ge=0, le=100)
    xp: int = Field(default=0, ge=0)
    version: int = 0
    updated_at: datetime
    last_action_at: datetime | None = None
    sleep_started_at: datetime | None = None


class GameError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


DECAY_PER_HOUR = {"satiety": 4, "happiness": 3, "energy": 2, "hygiene": 3}
COOLDOWN_SECONDS = 10
SLEEP_SECONDS = 30 * 60
SLEEP_TICK_SECONDS = 10 * 60
MILESTONES = ((2, "Знакомые"), (5, "Друзья"), (10, "Неразлучные"))
REWARDS = {
    Action.feed: {"satiety": 25},
    Action.play: {"happiness": 25, "energy": -15, "satiety": -5},
    Action.wash: {"hygiene": 30},
    Action.rest: {"energy": 0},
}


def evolve(pet: Pet, now: datetime) -> Pet:
    end = max(now, pet.updated_at)
    cursor = pet.updated_at
    updates = {stat: getattr(pet, stat) for stat in DECAY_PER_HOUR}
    start = pet.sleep_started_at
    wake = start + timedelta(seconds=SLEEP_SECONDS) if start else None

    def decay(until: datetime):
        nonlocal cursor
        seconds = (until - cursor).total_seconds()
        asleep = max(0, (min(until, wake) - max(cursor, start)).total_seconds()) if start else 0
        hours = (seconds - asleep + asleep / 4) / 3600
        for stat, rate in DECAY_PER_HOUR.items():
            stat_hours = (
                (seconds - asleep) / 3600 if stat == "energy" and updates[stat] == 100 else hours
            )
            updates[stat] = max(0, updates[stat] - rate * stat_hours)
        cursor = until

    # Apply each reward at its actual time so caps and later decay remain correct.
    if start:
        for offset in range(SLEEP_TICK_SECONDS, SLEEP_SECONDS + 1, SLEEP_TICK_SECONDS):
            tick = start + timedelta(seconds=offset)
            if cursor < tick <= end:
                decay(tick)
                updates["energy"] = min(100, updates["energy"] + 8)
    decay(end)
    return pet.model_copy(update={**updates, "updated_at": end})


def sleep_remaining(pet: Pet, now: datetime) -> float:
    if pet.sleep_started_at is None:
        return 0.0
    return max(0, SLEEP_SECONDS - (now - pet.sleep_started_at).total_seconds())


def act(pet: Pet, action: Action, now: datetime) -> Pet:
    current = evolve(pet, now)
    if action == Action.wake:
        if sleep_remaining(current, now) <= 0:
            raise GameError("Питомец уже не спит")
        if current.energy < 100:
            raise GameError("Питомец ещё спит: дождитесь полной энергии")
        return current.model_copy(update={
            "sleep_started_at": None, "version": pet.version + 1, "last_action_at": now,
        })
    if sleep_remaining(pet, now) > 0:
        raise GameError("Питомец спит: действия будут доступны после 30 минут сна")
    if pet.last_action_at and (now - pet.last_action_at).total_seconds() < COOLDOWN_SECONDS:
        raise GameError("Питомцу нужна пауза: между действиями 10 секунд", 429)
    if action == Action.play and current.energy < 15:
        raise GameError("Сначала нужно отдохнуть")
    effects = REWARDS[action]
    # A full stat should not become an unlimited source of experience.
    primary = next(iter(effects))
    if getattr(current, primary) > 95:
        raise GameError("Пока не нужно: этот показатель почти полный")
    updates = {
        stat: min(100, max(0, getattr(current, stat) + delta))
        for stat, delta in effects.items()
    }
    return current.model_copy(update={
        **updates,
        "xp": current.xp + 10,
        "version": pet.version + 1,
        "last_action_at": now,
        "sleep_started_at": now if action == Action.rest else current.sleep_started_at,
    })


def mood_for(pet: Pet, now: datetime) -> str:
    current = evolve(pet, now)
    if sleep_remaining(current, now) > 0:
        return "sleeping"
    needs = (("satiety", "hungry"), ("energy", "tired"),
             ("hygiene", "dirty"), ("happiness", "lonely"))
    stat, mood = min(needs, key=lambda item: getattr(current, item[0]))
    if getattr(current, stat) < 30:
        return mood
    return "happy" if all(getattr(current, s) >= 70 for s, _ in needs) else "calm"


def present(pet: Pet, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    current = evolve(pet, now)
    remaining = 0.0
    if current.last_action_at:
        remaining = max(0, COOLDOWN_SECONDS - (now - current.last_action_at).total_seconds())
    sleeping_seconds = sleep_remaining(current, now)
    level = 1 + current.xp // 100
    title = "Первая встреча"
    next_milestone = None
    for target, milestone_title in MILESTONES:
        if level >= target:
            title = milestone_title
        else:
            next_milestone = {
                "level": target, "title": milestone_title,
                "xp_remaining": (target - 1) * 100 - current.xp,
            }
            break
    return {
        "name": current.name,
        "species": current.species,
        "needs_name": not current.name_chosen,
        "stats": {stat: round(getattr(current, stat), 1) for stat in DECAY_PER_HOUR},
        "xp": current.xp,
        "level": level,
        "mood": mood_for(current, now),
        "current_title": title,
        "next_milestone": next_milestone,
        "cooldown_seconds": max(remaining, sleeping_seconds),
        "sleep_remaining_seconds": sleeping_seconds,
        "can_wake": sleeping_seconds > 0 and current.energy >= 100,
    }
