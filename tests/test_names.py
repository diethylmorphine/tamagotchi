from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from backend.auth import telegram_user
from backend.game import Pet
from main import app, repository


@pytest.fixture
def client():
    class Repository:
        pet = Pet(telegram_id=7, xp=150, updated_at=datetime.now(UTC))

        async def get_or_create(self, user_id):
            assert user_id == self.pet.telegram_id
            return self.pet

        async def save(self, pet, previous_version):
            assert previous_version == self.pet.version
            self.pet = pet
            return True

    repo = Repository()
    app.dependency_overrides[telegram_user] = lambda: 7
    app.dependency_overrides[repository] = lambda: repo
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_first_name_and_rename_preserve_progress(client):
    assert client.get('/api/pet').json()['needs_name'] is True
    response = client.patch('/api/pet/name', json={'name': '  Пиксель  '})
    assert response.status_code == 200
    assert response.json()['name'] == 'Пиксель'
    assert response.json()['needs_name'] is False
    assert response.json()['xp'] == 150
    response = client.patch('/api/pet/name', json={'name': 'Луна'})
    assert response.json()['name'] == 'Луна'
    assert client.get('/api/pet').json()['name'] == 'Луна'
    assert response.json()['xp'] == 150


@pytest.mark.parametrize('name', ['', '   ', 'я' * 25, 'bad\nname', 'bad\u200bname'])
def test_invalid_names(client, name):
    assert client.patch('/api/pet/name', json={'name': name}).status_code == 422
    assert client.get('/api/pet').json()['needs_name'] is True


def test_rename_requires_auth():
    with TestClient(app) as client:
        assert client.patch('/api/pet/name', json={'name': 'Луна'}).status_code == 401
