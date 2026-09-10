"""Pure game rules. Only the server decides time, stats and rewards."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Action(StrEnum):
    feed = "feed"
    play = "play"
    wash = "wash"
    rest = "rest"


class Pet(BaseModel):
    telegram_id: int
    name: str = "Моти"
    name_chosen: bool = False
    satiety: float = Field(default=80, ge=0, le=100)
    happiness: float = Field(default=80, ge=0, le=100)
    energy: float = Field(default=80, ge=0, le=100)
    hygiene: float = Field(default=80, ge=0, le=100)
    xp: int = Field(default=0, ge=0)
    version: int = 0
    updated_at: datetime
    last_action_at: datetime | None = None


class GameError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


DECAY_PER_HOUR = {"satiety": 4, "happiness": 3, "energy": 2, "hygiene": 3}
COOLDOWN_SECONDS = 10
REWARDS = {
    Action.feed: {"satiety": 25},
    Action.play: {"happiness": 25, "energy": -15, "satiety": -5},
    Action.wash: {"hygiene": 30},
    Action.rest: {"energy": 30},
}


def evolve(pet: Pet, now: datetime) -> Pet:
    elapsed = max(0, (now - pet.updated_at).total_seconds()) / 3600
    updates = {
        stat: max(0, getattr(pet, stat) - rate * elapsed)
        for stat, rate in DECAY_PER_HOUR.items()
    }
    return pet.model_copy(update={**updates, "updated_at": max(now, pet.updated_at)})


def act(pet: Pet, action: Action, now: datetime) -> Pet:
    if pet.last_action_at and (now - pet.last_action_at).total_seconds() < COOLDOWN_SECONDS:
        raise GameError("Питомцу нужна пауза: между действиями 10 секунд", 429)
    current = evolve(pet, now)
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
    })


def present(pet: Pet, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    current = evolve(pet, now)
    remaining = 0.0
    if current.last_action_at:
        remaining = max(0, COOLDOWN_SECONDS - (now - current.last_action_at).total_seconds())
    return {
        "name": current.name,
        "needs_name": not current.name_chosen,
        "stats": {stat: round(getattr(current, stat), 1) for stat in DECAY_PER_HOUR},
        "xp": current.xp,
        "level": 1 + current.xp // 100,
        "cooldown_seconds": remaining,
    }
