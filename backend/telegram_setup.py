"""Telegram webhook setup shared by local tooling and authenticated operations."""

import re

from aiogram import Bot
from aiogram.types import MenuButtonWebApp, WebAppInfo

from backend.config import Settings

ALLOWED_UPDATES = ["message", "callback_query"]


async def configure_telegram(bot: Bot, settings: Settings):
    url = str(settings.webapp_url).rstrip("/")
    secret = settings.webhook_secret.get_secret_value()
    if not url.startswith("https://"):
        raise ValueError("Telegram requires an HTTPS WEBAPP_URL")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", secret):
        raise ValueError("WEBHOOK_SECRET: use 16–256 letters, numbers, underscores or hyphens")
    await bot.set_webhook(
        url=f"{url}/api/telegram/webhook", secret_token=secret,
        allowed_updates=ALLOWED_UPDATES, drop_pending_updates=False,
    )
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
        text="Мой питомец", web_app=WebAppInfo(url=url),
    ))


async def webhook_status(bot: Bot, settings: Settings) -> dict:
    info = await bot.get_webhook_info()
    expected = str(settings.webapp_url).rstrip("/") + "/api/telegram/webhook"
    return {
        "webhook_matches_app": info.url == expected,
        "allowed_updates": info.allowed_updates,
        "pending_updates": info.pending_update_count,
        "last_error_at": info.last_error_date.isoformat() if info.last_error_date else None,
        "has_delivery_error": bool(info.last_error_message),
    }
