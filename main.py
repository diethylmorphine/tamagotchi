import secrets
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import httpx
from aiogram import Bot
from aiogram.types import Update
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from backend.auth import telegram_user
from backend.bot import dispatcher
from backend.config import get_settings
from backend.game import Action, GameError, act, present
from backend.repository import PetRepository

app = FastAPI(title="Tamagotchi-Fawn API", version="0.1.0")
FRONTEND = Path(__file__).parent / "frontend"
app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(GameError)
async def game_error(_request, exc: GameError):
    headers = {"Retry-After": "10"} if exc.status == 429 else {}
    return JSONResponse({"detail": str(exc)}, status_code=exc.status, headers=headers)


async def repository():
    async with httpx.AsyncClient(timeout=10) as client:
        yield PetRepository(client)


@app.get("/api/pet")
async def get_pet(
    response: Response,
    user_id: int = Depends(telegram_user),
    repo: PetRepository = Depends(repository),
):
    response.headers["Cache-Control"] = "no-store"
    return present(await repo.get_or_create(user_id))


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
