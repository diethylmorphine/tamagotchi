from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.auth import telegram_user
from backend.game import Pet
from main import app, repository


def test_species_switch_preserves_progress_sleep_and_name():
    class Repository:
        pet = Pet(
            telegram_id=7, name="Луна", name_chosen=True, xp=664, version=3,
            satiety=42, updated_at=datetime.now(UTC), sleep_started_at=datetime.now(UTC),
        )

        async def get_or_create(self, user_id):
            assert user_id == 7
            return self.pet

        async def save(self, pet, previous_version):
            assert previous_version == self.pet.version
            self.pet = pet
            return True

    repo = Repository()
    before = repo.pet.model_dump()
    app.dependency_overrides[telegram_user] = lambda: 7
    app.dependency_overrides[repository] = lambda: repo
    try:
        with TestClient(app) as client:
            for species in ("fox", "cat"):
                response = client.patch("/api/pet/species", json={"species": species})
                assert response.status_code == 200
                assert response.json()["species"] == species
                assert client.get("/api/pet").json()["species"] == species
                for key in before.keys() - {"species", "version"}:
                    assert repo.pet.model_dump()[key] == before[key]
            version = repo.pet.version
            client.patch("/api/pet/species", json={"species": "cat"})
            assert repo.pet.version == version  # Selecting current pet is a no-op.
            assert client.patch("/api/pet/species", json={"species": "wolf"}).status_code == 422
            assert client.patch("/api/pet/species", json={
                "species": "fox", "telegram_id": 8,
            }).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_species_retries_from_fresh_state_after_conflict():
    class Repository:
        pet = Pet(telegram_id=7, updated_at=datetime.now(UTC))
        calls = 0

        async def get_or_create(self, user_id):
            return self.pet

        async def save(self, pet, previous_version):
            self.calls += 1
            if self.calls == 1:
                self.pet = self.pet.model_copy(update={"xp": 10, "version": 1})
                return False
            assert previous_version == 1
            self.pet = pet
            return True

    repo = Repository()
    app.dependency_overrides[telegram_user] = lambda: 7
    app.dependency_overrides[repository] = lambda: repo
    try:
        with TestClient(app) as client:
            data = client.patch("/api/pet/species", json={"species": "fox"}).json()
            assert data["xp"] == 10
            assert data["species"] == "fox"
    finally:
        app.dependency_overrides.clear()


def test_species_requires_owner_auth():
    with TestClient(app) as client:
        assert client.patch("/api/pet/species", json={"species": "fox"}).status_code == 401
