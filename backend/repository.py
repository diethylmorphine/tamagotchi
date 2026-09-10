"""Supabase REST access. All writes use a version condition to avoid lost updates."""

import httpx
from fastapi import HTTPException

from backend.config import get_settings
from backend.game import Pet


class PetRepository:
    def __init__(self, client: httpx.AsyncClient):
        settings = get_settings()
        self.client = client
        self.url = f"{str(settings.supabase_url).rstrip('/')}/rest/v1/pets"
        key = settings.supabase_service_role_key.get_secret_value()
        self.headers = {"apikey": key, "Authorization": f"Bearer {key}"}

    async def request(self, method: str, **kwargs) -> httpx.Response:
        headers = {**self.headers, **kwargs.pop("headers", {})}
        try:
            response = await self.client.request(method, self.url, headers=headers, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            # Never return database internals or credentials to the client.
            raise HTTPException(503, "База временно недоступна, попробуйте позже") from exc

    async def get_or_create(self, user_id: int) -> Pet:
        params = {"telegram_id": f"eq.{user_id}", "select": "*"}
        response = await self.request("GET", params=params)
        rows = response.json()
        if rows:
            return Pet.model_validate(rows[0])
        # ON CONFLICT DO NOTHING makes simultaneous first visits safe.
        await self.request(
            "POST", params={"on_conflict": "telegram_id"},
            headers={"Prefer": "resolution=ignore-duplicates,return=minimal"},
            json={"telegram_id": user_id},
        )
        response = await self.request("GET", params=params)
        return Pet.model_validate(response.json()[0])

    async def save(self, pet: Pet, previous_version: int) -> bool:
        response = await self.request(
            "PATCH",
            params={"telegram_id": f"eq.{pet.telegram_id}", "version": f"eq.{previous_version}"},
            headers={"Prefer": "return=representation"},
            json=pet.model_dump(mode="json", exclude={"telegram_id"}),
        )
        return bool(response.json())

