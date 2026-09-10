from datetime import UTC, datetime

from aiogram.utils.web_app import safe_parse_webapp_init_data
from fastapi import Depends, Header, HTTPException

from backend.config import get_settings


def authenticated_profile(init_data: str, token: str, ttl: int, now: datetime | None = None):
    try:
        data = safe_parse_webapp_init_data(token=token, init_data=init_data)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(401, "Некорректная Telegram-авторизация") from exc
    age = ((now or datetime.now(UTC)) - data.auth_date).total_seconds()
    if age < -30 or age > ttl or data.user is None or data.user.id <= 0:
        raise HTTPException(401, "Откройте мини-приложение заново через Telegram")
    return data.user


def authenticate(init_data: str, token: str, ttl: int, now: datetime | None = None) -> int:
    return authenticated_profile(init_data, token, ttl, now).id


def telegram_profile(authorization: str = Header(default="", max_length=16384)):
    scheme, _, payload = authorization.partition(" ")
    if scheme.lower() != "tma" or not payload:
        raise HTTPException(401, "Откройте игру через Telegram-бота")
    settings = get_settings()
    return authenticated_profile(
        payload, settings.bot_token.get_secret_value(), settings.init_data_ttl_seconds
    )


def telegram_user(profile=Depends(telegram_profile)) -> int:
    return profile.id


def admin_user(user_id: int = Depends(telegram_user)) -> int:
    if user_id not in get_settings().admin_telegram_ids:
        raise HTTPException(403, "Доступ только для администраторов")
    return user_id
