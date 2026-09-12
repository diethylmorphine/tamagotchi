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


@pytest.mark.parametrize('action', list(Action))
def test_sleep_blocks_every_action_until_wakeup(action):
    sleeping = act(Pet(telegram_id=1, updated_at=NOW), Action.rest, NOW)
    assert sleeping.energy == 80
    with pytest.raises(GameError, match='спит'):
        act(sleeping, action, NOW + timedelta(minutes=29, seconds=59))
    assert present(sleeping, NOW)['cooldown_seconds'] == 1800
    assert act(sleeping, Action.wash, NOW + timedelta(minutes=30)).hygiene == 100


@pytest.mark.parametrize('minutes,rewards', [(9, 0), (10, 8), (20, 16), (30, 24), (60, 24)])
def test_sleep_decay_and_energy_ticks(minutes, rewards):
    sleeping = act(Pet(telegram_id=1, energy=40, updated_at=NOW), Action.rest, NOW)
    current = evolve(sleeping, NOW + timedelta(minutes=minutes))
    hours = (min(minutes, 30) / 4 + max(0, minutes - 30)) / 60
    assert current.energy == pytest.approx(40 + rewards - 2 * hours)
    assert current.satiety == pytest.approx(80 - 4 * hours)
    assert current.happiness == pytest.approx(80 - 3 * hours)
    assert current.hygiene == pytest.approx(80 - 3 * hours)
    remaining = present(current, current.updated_at)['sleep_remaining_seconds']
    assert remaining == max(0, 1800 - minutes * 60)


def test_sleep_incremental_reads_match_offline_including_energy_cap():
    sleeping = act(Pet(telegram_id=1, energy=94, updated_at=NOW), Action.rest, NOW)
    incremental = sleeping
    for minute in range(61):
        incremental = evolve(incremental, NOW + timedelta(minutes=minute))
    offline = evolve(sleeping, NOW + timedelta(hours=1))
    assert incremental.energy == pytest.approx(offline.energy)
    assert offline.energy == 99
    assert evolve(offline, offline.updated_at) == offline
    assert evolve(sleeping, NOW - timedelta(seconds=1)) == sleeping


def test_new_sleep_has_its_own_ticks():
    pet = Pet(telegram_id=1, energy=20, updated_at=NOW)
    first = act(pet, Action.rest, NOW)
    second = act(first, Action.rest, NOW + timedelta(minutes=30))
    assert second.energy == pytest.approx(43.75)
    assert evolve(second, NOW + timedelta(minutes=40)).energy == pytest.approx(51.75 - 1 / 12)
