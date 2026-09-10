from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.auth import telegram_profile, telegram_user
from backend.game import Pet
from main import app, repository


@pytest.fixture
def admin_client(monkeypatch):
    settings = SimpleNamespace(admin_telegram_ids=[7])
    monkeypatch.setattr('backend.auth.get_settings', lambda: settings)
    monkeypatch.setattr('main.get_settings', lambda: settings)

    class Repository:
        pet = Pet(
            telegram_id=8, name='Луна', owner_name='Анна', owner_username='anna',
            xp=150, updated_at=datetime.now(UTC) - timedelta(hours=1),
        )
        conflict = False
        profile = None

        async def get(self, user_id):
            if user_id != self.pet.telegram_id:
                raise HTTPException(404, 'Питомец пользователя не найден')
            return self.pet

        async def list_pets(self, after, limit):
            return [self.pet] if after < self.pet.telegram_id else []

        async def save(self, pet, previous_version):
            assert previous_version == self.pet.version
            if self.conflict:
                return False
            self.pet = pet
            return True

        async def record_profile(self, user_id, name, username):
            self.profile = (user_id, name, username)

    repo = Repository()
    app.dependency_overrides[telegram_user] = lambda: 7
    app.dependency_overrides[repository] = lambda: repo
    try:
        with TestClient(app) as client:
            yield client, repo
    finally:
        app.dependency_overrides.clear()


def test_list_names_and_lookup(admin_client):
    client, _ = admin_client
    response = client.get('/api/admin/pets')
    assert response.headers['cache-control'] == 'no-store'
    pet = response.json()['items'][0]
    assert (pet['owner_name'], pet['owner_username'], pet['name']) == ('Анна', 'anna', 'Луна')
    assert pet['telegram_id'] == '8'
    assert client.get('/api/admin/pets/8').status_code == 200
    assert client.get('/api/admin/pets/9').status_code == 404
    assert client.get('/api/admin/pets?after=8').json()['items'] == []


def test_edit_preserves_progress_and_evolves_untouched_stats(admin_client):
    client, repo = admin_client
    response = client.patch('/api/admin/pets/8', json={
        'version': 0, 'level': 10, 'satiety': 100, 'energy': 0,
    })
    assert response.status_code == 200
    pet = response.json()
    assert pet['level'] == 10 and pet['xp'] == 950
    assert pet['stats']['satiety'] == 100 and pet['stats']['energy'] == 0
    assert pet['stats']['happiness'] == 77 and pet['stats']['hygiene'] == 77
    assert pet['version'] == 1 and pet['name'] == 'Луна'
    assert repo.pet.last_action_at is None
    assert (datetime.now(UTC) - repo.pet.updated_at).total_seconds() < 5
    response = client.patch('/api/admin/pets/8', json={'version': 1, 'hygiene': 100})
    assert response.json()['xp'] == 950


@pytest.mark.parametrize('changes', [
    {}, {'level': 0}, {'level': 1_000_001}, {'level': 1.5}, {'satiety': -1},
    {'happiness': 101}, {'energy': None}, {'hygiene': 'NaN'}, {'xp': 100},
    {'telegram_id': 9}, {'owner_name': 'Подмена'},
])
def test_invalid_changes(admin_client, changes):
    client, repo = admin_client
    response = client.patch('/api/admin/pets/8', json={'version': 0, **changes})
    assert response.status_code == 422
    assert repo.pet.version == 0


def test_stale_and_concurrent_writes(admin_client):
    client, repo = admin_client
    assert client.patch('/api/admin/pets/8', json={
        'version': 1, 'level': 3,
    }).status_code == 409
    repo.conflict = True
    assert client.patch('/api/admin/pets/8', json={
        'version': 0, 'level': 3,
    }).status_code == 409
    assert repo.pet.xp == 150


def test_non_admin_cannot_read_or_write(admin_client):
    client, repo = admin_client
    app.dependency_overrides[telegram_user] = lambda: 8
    assert client.get('/api/admin/pets').status_code == 403
    assert client.get('/api/admin/pets/8').status_code == 403
    assert client.patch('/api/admin/pets/8', json={
        'version': 0, 'level': 3,
    }).status_code == 403
    assert repo.pet.xp == 150


def test_admin_routes_require_authentication():
    with TestClient(app) as client:
        assert client.get('/api/admin/pets').status_code == 401
        assert client.get('/api/admin/pets/8').status_code == 401
        assert client.patch('/api/admin/pets/8', json={
            'version': 0, 'level': 3,
        }).status_code == 401


def test_session_saves_verified_profile(admin_client):
    client, repo = admin_client
    app.dependency_overrides[telegram_profile] = lambda: SimpleNamespace(
        id=7, first_name='Иван', last_name='Петров', username='ivan',
    )
    response = client.get('/api/session')
    assert response.json() == {'is_admin': True}
    assert response.headers['cache-control'] == 'no-store'
    assert repo.profile == (7, 'Иван Петров', 'ivan')


def test_pagination_cursor(admin_client):
    client, repo = admin_client

    async def list_pets(after, limit):
        return [
            repo.pet.model_copy(update={'telegram_id': user_id})
            for user_id in range(8, 12) if user_id > after
        ][:limit]

    repo.list_pets = list_pets
    page = client.get('/api/admin/pets?limit=2').json()
    assert [pet['telegram_id'] for pet in page['items']] == ['8', '9']
    assert page['next_after'] == '9'
    page = client.get('/api/admin/pets?limit=2&after=9').json()
    assert [pet['telegram_id'] for pet in page['items']] == ['10', '11']
    assert page['next_after'] is None
