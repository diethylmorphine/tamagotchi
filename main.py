import secrets
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from aiogram import Bot
from aiogram.types import Update
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.auth import admin_user, telegram_profile, telegram_user
from backend.bot import dispatcher, pet_keyboard
from backend.config import get_settings
from backend.game import Action, GameError, act, evolve, present
from backend.reminders import ReminderRepository, send_reminders
from backend.repository import PetRepository
from backend.telegram_setup import configure_telegram, webhook_status

app = FastAPI(title="Tamagotchi-Fawn API", version="0.1.0")
FRONTEND = Path(__file__).parent / "frontend"
app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/cron/reminders")
async def cron_reminders(authorization: str = Header(default="")):
    settings = get_settings()
    if not settings.cron_secret or not secrets.compare_digest(
        authorization, f"Bearer {settings.cron_secret.get_secret_value()}",
    ):
        raise HTTPException(403, "Forbidden")
    async with httpx.AsyncClient(timeout=10) as client:
        async with Bot(token=settings.bot_token.get_secret_value()) as bot:
            repo = ReminderRepository(client)
            started = datetime.now(UTC)
            await repo.start_run(started)
            result = await send_reminders(repo, bot, pet_keyboard())
            await repo.finish_run(started, result)
            return result


@app.get("/api/cron/telegram")
async def telegram_status(authorization: str = Header(default="")):
    settings = get_settings()
    if not settings.cron_secret or not secrets.compare_digest(
        authorization, f"Bearer {settings.cron_secret.get_secret_value()}",
    ):
        raise HTTPException(403, "Forbidden")
    async with Bot(token=settings.bot_token.get_secret_value()) as bot:
        return await webhook_status(bot, settings)


@app.post("/api/cron/telegram")
async def repair_telegram(authorization: str = Header(default="")):
    settings = get_settings()
    if not settings.cron_secret or not secrets.compare_digest(
        authorization, f"Bearer {settings.cron_secret.get_secret_value()}",
    ):
        raise HTTPException(403, "Forbidden")
    async with Bot(token=settings.bot_token.get_secret_value()) as bot:
        await configure_telegram(bot, settings)
        return await webhook_status(bot, settings)


@app.exception_handler(GameError)
async def game_error(_request, exc: GameError):
    headers = {"Retry-After": "10"} if exc.status == 429 else {}
    return JSONResponse({"detail": str(exc)}, status_code=exc.status, headers=headers)


async def repository():
    async with httpx.AsyncClient(timeout=10) as client:
        yield PetRepository(client)


async def reminder_repository():
    async with httpx.AsyncClient(timeout=10) as client:
        yield ReminderRepository(client)


async def delivery_status(repo: ReminderRepository):
    configured = bool(get_settings().cron_secret)
    state = await repo.scheduler_status() if configured else {
        "scheduler_healthy": False, "last_run_at": None,
    }
    return {"configured": configured, **state}


@app.get("/api/reminders")
async def reminder_status(
    response: Response,
    user_id: int = Depends(telegram_user),
    repo: ReminderRepository = Depends(reminder_repository),
):
    response.headers["Cache-Control"] = "no-store"
    return {
        "enabled": await repo.is_enabled(user_id),
        **await delivery_status(repo),
    }


class ReminderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(strict=True)


@app.patch("/api/reminders")
async def update_reminders(
    body: ReminderRequest,
    user_id: int = Depends(telegram_user),
    repo: PetRepository = Depends(repository),
    reminders: ReminderRepository = Depends(reminder_repository),
):
    await repo.get_or_create(user_id)
    await reminders.enable(user_id, body.enabled)
    return {"enabled": body.enabled, **await delivery_status(reminders)}


@app.get("/api/session")
async def session(
    response: Response,
    profile=Depends(telegram_profile),
    repo: PetRepository = Depends(repository),
):
    response.headers["Cache-Control"] = "no-store"
    name = " ".join(part for part in (profile.first_name, profile.last_name) if part)
    await repo.record_profile(profile.id, name, profile.username)
    return {"is_admin": profile.id in get_settings().admin_telegram_ids}


def admin_present(pet):
    return {
        **present(pet), "telegram_id": str(pet.telegram_id), "version": pet.version,
        "owner_name": pet.owner_name, "owner_username": pet.owner_username,
    }


@app.get("/api/admin/pets", dependencies=[Depends(admin_user)])
async def admin_pets(
    response: Response,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    repo: PetRepository = Depends(repository),
):
    response.headers["Cache-Control"] = "no-store"
    rows = await repo.list_pets(after, limit + 1)
    return {
        "items": [admin_present(pet) for pet in rows[:limit]],
        "next_after": str(rows[limit - 1].telegram_id) if len(rows) > limit else None,
    }


@app.get("/api/admin/pets/{user_id}", dependencies=[Depends(admin_user)])
async def admin_get_pet(
    user_id: int, response: Response, repo: PetRepository = Depends(repository),
):
    response.headers["Cache-Control"] = "no-store"
    return admin_present(await repo.get(user_id))


class AdminPetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0, strict=True)
    level: int | None = Field(default=None, ge=1, le=1_000_000, strict=True)
    satiety: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    happiness: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    energy: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    hygiene: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_changes(self):
        fields = self.model_fields_set - {"version"}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError("Укажите уровень или показатели; пустые значения недопустимы")
        return self


@app.patch("/api/admin/pets/{user_id}", dependencies=[Depends(admin_user)])
async def admin_update_pet(
    user_id: int, body: AdminPetRequest, repo: PetRepository = Depends(repository),
):
    pet = await repo.get(user_id)
    conflict = "Питомец уже обновился. Загрузите актуальное состояние перед сохранением"
    if pet.version != body.version:
        raise HTTPException(409, conflict)
    changes = body.model_dump(exclude_unset=True, exclude={"version", "level"})
    if body.level is not None:
        changes["xp"] = (body.level - 1) * 100 + pet.xp % 100
    updated = evolve(pet, datetime.now(UTC)).model_copy(update={
        **changes, "version": pet.version + 1,
    })
    if not await repo.save(updated, previous_version=pet.version):
        raise HTTPException(409, conflict)
    return admin_present(updated)


@app.get("/api/pet")
async def get_pet(
    response: Response,
    user_id: int = Depends(telegram_user),
    repo: PetRepository = Depends(repository),
):
    response.headers["Cache-Control"] = "no-store"
    return present(await repo.get_or_create(user_id))


@app.get("/api/leaderboard", dependencies=[Depends(telegram_user)])
async def leaderboard(response: Response, repo: PetRepository = Depends(repository)):
    response.headers["Cache-Control"] = "no-store"
    return {"items": [
        {"name": pet["name"], "xp": pet["xp"], "level": 1 + pet["xp"] // 100}
        for pet in await repo.top_pets()
    ]}


class ActionRequest(BaseModel):
    action: Action


class NameRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = unicodedata.normalize("NFC", value).strip()
        if not 1 <= len(value) <= 24:
            raise ValueError("Имя должно содержать от 1 до 24 символов")
        if any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("В имени недопустимы управляющие символы")
        return value


class SpeciesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    species: Literal["cat", "fox"]


@app.patch("/api/pet/species")
async def change_species(
    body: SpeciesRequest,
    user_id: int = Depends(telegram_user),
    repo: PetRepository = Depends(repository),
):
    for _ in range(3):
        pet = await repo.get_or_create(user_id)
        if pet.species == body.species:
            return present(pet)
        updated = pet.model_copy(update={
            "species": body.species, "version": pet.version + 1,
        })
        if await repo.save(updated, previous_version=pet.version):
            return present(updated)
    raise HTTPException(409, "Питомец уже обновился. Повторите выбор")


@app.patch("/api/pet/name")
async def rename_pet(
    body: NameRequest,
    user_id: int = Depends(telegram_user),
    repo: PetRepository = Depends(repository),
):
    for _ in range(3):
        pet = await repo.get_or_create(user_id)
        updated = pet.model_copy(update={
            "name": body.name, "name_chosen": True, "version": pet.version + 1,
        })
        if await repo.save(updated, previous_version=pet.version):
            return present(updated)
    raise HTTPException(409, "Питомец уже обновился. Повторите сохранение")


@app.post("/api/pet/actions")
async def pet_action(
    body: ActionRequest,
    user_id: int = Depends(telegram_user),
    repo: PetRepository = Depends(repository),
):
    for _ in range(3):
        pet = await repo.get_or_create(user_id)
        updated = act(pet, body.action, datetime.now(UTC))
        if await repo.save(updated, previous_version=pet.version):
            return present(updated)
    raise HTTPException(409, "Питомец уже обновился. Повторите действие")


@app.post("/api/telegram/webhook")
async def telegram_webhook(
    update: Update,
    x_telegram_bot_api_secret_token: str = Header(default=""),
):
    settings = get_settings()
    if not secrets.compare_digest(
        x_telegram_bot_api_secret_token, settings.webhook_secret.get_secret_value()
    ):
        raise HTTPException(403, "Forbidden")
    # Await handlers: background tasks may be stopped after a serverless response.
    async with Bot(token=settings.bot_token.get_secret_value()) as bot:
        await dispatcher.feed_update(bot, update)
    return {"ok": True}
