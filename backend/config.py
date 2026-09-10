from functools import lru_cache

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: SecretStr
    webapp_url: HttpUrl
    webhook_secret: SecretStr = Field(min_length=16)
    supabase_url: HttpUrl
    supabase_service_role_key: SecretStr
    init_data_ttl_seconds: int = Field(default=3600, ge=60, le=86400)


@lru_cache
def get_settings() -> Settings:
    return Settings()

