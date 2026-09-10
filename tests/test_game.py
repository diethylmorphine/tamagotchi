from datetime import UTC, datetime, timedelta

import pytest

from backend.game import Action, GameError, Pet, act, evolve, present

NOW = datetime(2026, 9, 10, tzinfo=UTC)


def test_offline_decay_and_floor():
    pet = Pet(telegram_id=1, updated_at=NOW)
    assert evolve(pet, NOW + timedelta(hours=2)).satiety == 72
    assert evolve(pet, NOW + timedelta(days=100)).energy == 0
    assert pet.satiety == 80


def test_reads_do_not_double_count_decay():
    pet = Pet(telegram_id=1, updated_at=NOW)
    later = NOW + timedelta(hours=2)
    assert evolve(evolve(pet, later), later) == evolve(pet, later)


def test_action_rewards_and_cooldown():
    pet = Pet(telegram_id=1, updated_at=NOW)
    fed = act(pet, Action.feed, NOW)
    assert (fed.satiety, fed.xp, fed.version) == (100, 10, 1)
    with pytest.raises(GameError) as exc:
        act(fed, Action.wash, NOW + timedelta(seconds=9))
    assert exc.value.status == 429
    assert act(fed, Action.wash, NOW + timedelta(seconds=10)).xp == 20


def test_play_requires_energy_and_full_stat_does_not_reward():
    with pytest.raises(GameError):
        act(Pet(telegram_id=1, energy=10, updated_at=NOW), Action.play, NOW)
    with pytest.raises(GameError):
        act(Pet(telegram_id=1, satiety=100, updated_at=NOW), Action.feed, NOW)


def test_level_and_clock_skew():
    pet = Pet(telegram_id=1, xp=100, updated_at=NOW)
    assert present(pet, NOW)['level'] == 2
    assert evolve(pet, NOW - timedelta(hours=1)).updated_at == NOW

