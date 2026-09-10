from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.auth import telegram_user
from backend.game import Pet
from main import app, repository


def test_public_routes_and_auth_required():
    with TestClient(app) as client:
        assert client.get('/api/health').json() == {'status': 'ok'}
        assert client.get('/').status_code == 200
        assert client.get('/assets/app.js').status_code == 200
        assert client.get('/api/pet').status_code == 401
        assert client.post('/api/pet/actions', json={'action': 'feed'}).status_code == 401


def test_concurrent_conflict_rechecks_cooldown():
    class ConflictingRepository:
        def __init__(self):
            self.pet = Pet(telegram_id=7, updated_at=datetime.now(UTC))

        async def get_or_create(self, user_id):
            assert user_id == 7
            return self.pet

        async def save(self, pet, previous_version):
            assert previous_version == 0
            # Simulate another request winning the conditional database update.
            self.pet = pet
            return False

    repo = ConflictingRepository()
    app.dependency_overrides[telegram_user] = lambda: 7
    app.dependency_overrides[repository] = lambda: repo
    try:
        with TestClient(app) as client:
            response = client.post('/api/pet/actions', json={'action': 'feed'})
            assert response.status_code == 429
            assert repo.pet.xp == 10
            assert client.post('/api/pet/actions', json={'action': 'cheat'}).status_code == 422
    finally:
        app.dependency_overrides.clear()

