"""Run explicitly after deployment: python -m scripts.set_webhook."""

import asyncio
import re

from aiogram import Bot
from aiogram.types import MenuButtonWebApp, WebAppInfo

from backend.config import get_settings


async def main():
    settings = get_settings()
    url = str(settings.webapp_url).rstrip("/")
    secret = settings.webhook_secret.get_secret_value()
    if not url.startswith("https://"):
        raise ValueError("Telegram requires an HTTPS WEBAPP_URL")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", secret):
        raise ValueError("WEBHOOK_SECRET: use 16–256 letters, numbers, underscores or hyphens")
    async with Bot(token=settings.bot_token.get_secret_value()) as bot:
        await bot.set_webhook(
            url=f"{url}/api/telegram/webhook", secret_token=secret,
            allowed_updates=["message"],
        )
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
            text="Мой питомец", web_app=WebAppInfo(url=url),
        ))
        info = await bot.get_webhook_info()
        print(f"Webhook: {info.url}; pending updates: {info.pending_update_count}")


if __name__ == "__main__":
    asyncio.run(main())

