from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.auth import telegram_user
from backend.repository import PetRepository
from main import app, repository


@pytest.mark.parametrize('rows', [[], [{'name': 'Луна', 'xp': 250}]])
def test_leaderboard_for_regular_player(monkeypatch, rows):
    monkeypatch.setattr('backend.repository.get_settings', lambda: SimpleNamespace(
        supabase_url='https://example.test',
        supabase_service_role_key=SecretStr('test-key'),
    ))

    def respond(request):
        assert request.url.params['select'] == 'name,xp'
        assert request.url.params['order'] == 'xp.desc,telegram_id.asc'
        assert request.url.params['limit'] == '5'
        return httpx.Response(200, json=rows)

    async def repo():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            yield PetRepository(client)

    app.dependency_overrides[telegram_user] = lambda: 8
    app.dependency_overrides[repository] = repo
    try:
        with TestClient(app) as client:
            response = client.get('/api/leaderboard')
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'no-store'
            assert response.json() == {'items': [
                {'name': row['name'], 'xp': row['xp'], 'level': 1 + row['xp'] // 100}
                for row in rows
            ]}
    finally:
        app.dependency_overrides.clear()


def test_leaderboard_requires_authentication():
    with TestClient(app) as client:
        assert client.get('/api/leaderboard').status_code == 401
