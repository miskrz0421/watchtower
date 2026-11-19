"""Tests for the watcher states."""

from __future__ import annotations

from datetime import timedelta

import pytest

from watchtower import WatcherState
from watchtower.core import Active, Backoff, Disabled, Paused, State

_MINUTE = timedelta(minutes=1)


def _fail(state: State, times: int) -> State:
    """Return the state reached after `times` failed checks in a row."""
    for _ in range(times):
        state = state.after_failure()
    return state


def test_active_waits_the_interval() -> None:
    """Test that an active watcher is checked every interval."""
    assert Active().delay(_MINUTE) == _MINUTE


def test_active_stays_active_after_a_success() -> None:
    """Test that a successful check keeps a watcher active."""
    assert Active().after_success().kind is WatcherState.ACTIVE


def test_first_failure_starts_backoff() -> None:
    """Test that one failure moves an active watcher to backoff."""
    state = Active().after_failure()
    assert isinstance(state, Backoff)
    assert state.failures == 1


@pytest.mark.parametrize(("failures", "minutes"), [(1, 2), (2, 4), (3, 8), (4, 16)])
def test_backoff_doubles_the_wait_per_failure(failures: int, minutes: int) -> None:
    """Test that each failure in a row doubles the wait."""
    assert Backoff(failures).delay(_MINUTE) == timedelta(minutes=minutes)


def test_backoff_wait_is_capped_at_one_hour() -> None:
    """Test that the doubled wait never exceeds one hour."""
    assert Backoff(4).delay(timedelta(minutes=10)) == timedelta(hours=1)


def test_backoff_never_waits_less_than_the_interval() -> None:
    """Test that a watcher with an interval over an hour keeps its interval in backoff."""
    day = timedelta(days=1)
    assert Backoff(1).delay(day) == day


def test_backoff_needs_at_least_one_failure() -> None:
    """Test that a backoff without failures is refused."""
    with pytest.raises(ValueError, match="at least one failure"):
        Backoff(0)


def test_backoff_recovers_after_a_success() -> None:
    """Test that a successful check makes a backing-off watcher active again."""
    assert Backoff(3).after_success().kind is WatcherState.ACTIVE


def test_fourth_failure_in_a_row_still_backs_off() -> None:
    """Test that a watcher keeps backing off until its fifth failure."""
    state = _fail(Active(), 4)
    assert isinstance(state, Backoff)
    assert state.failures == 4


def test_fifth_failure_in_a_row_disables() -> None:
    """Test that the fifth failure in a row disables the watcher."""
    assert _fail(Active(), 5).kind is WatcherState.DISABLED


@pytest.mark.parametrize("state", [Paused(), Disabled()])
def test_paused_and_disabled_are_not_checked(state: State) -> None:
    """Test that paused and disabled watchers have no next check."""
    assert state.delay(_MINUTE) is None


@pytest.mark.parametrize("state", [Paused(), Disabled()])
def test_paused_and_disabled_keep_their_state_after_a_check(state: State) -> None:
    """Test that a check (e.g. CheckNow) does not change a paused or disabled watcher."""
    assert state.after_success() is state
    assert state.after_failure() is state
