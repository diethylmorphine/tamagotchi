"""Run explicitly after deployment: python -m scripts.set_webhook."""

import asyncio

from aiogram import Bot

from backend.config import get_settings
from backend.telegram_setup import configure_telegram, webhook_status


async def main():
    settings = get_settings()
    async with Bot(token=settings.bot_token.get_secret_value()) as bot:
        await configure_telegram(bot, settings)
        print(await webhook_status(bot, settings))


if __name__ == "__main__":
    asyncio.run(main())
