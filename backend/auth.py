from datetime import UTC, datetime

from aiogram.utils.web_app import safe_parse_webapp_init_data
from fastapi import Header, HTTPException

from backend.config import get_settings


def authenticate(init_data: str, token: str, ttl: int, now: datetime | None = None) -> int:
    try:
        data = safe_parse_webapp_init_data(token=token, init_data=init_data)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(401, "Некорректная Telegram-авторизация") from exc
    age = ((now or datetime.now(UTC)) - data.auth_date).total_seconds()
    if age < -30 or age > ttl or data.user is None or data.user.id <= 0:
        raise HTTPException(401, "Откройте мини-приложение заново через Telegram")
    return data.user.id


def telegram_user(authorization: str = Header(default="", max_length=16384)) -> int:
    scheme, _, payload = authorization.partition(" ")
    if scheme.lower() != "tma" or not payload:
        raise HTTPException(401, "Откройте игру через Telegram-бота")
    settings = get_settings()
    return authenticate(
        payload, settings.bot_token.get_secret_value(), settings.init_data_ttl_seconds
    )

