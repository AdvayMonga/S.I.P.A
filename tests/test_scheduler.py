from datetime import datetime
from pathlib import Path

import pytest
from servers.scheduler import store
from servers.scheduler.store import Task


def test_add_load_cancel(tmp_path: Path) -> None:
    task = store.add_task(tmp_path, "summarize my day", "daily")
    assert (tmp_path / "_system" / "Scheduled.md").is_file()
    loaded = store.load_tasks(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].prompt == "summarize my day"
    assert loaded[0].cadence == "daily"
    assert loaded[0].id == task.id

    assert store.cancel_task(tmp_path, task.id) is True
    assert store.load_tasks(tmp_path) == []
    assert store.cancel_task(tmp_path, "nope") is False


def test_invalid_cadence(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        store.add_task(tmp_path, "x", "hourly")


def test_load_missing_note(tmp_path: Path) -> None:
    assert store.load_tasks(tmp_path) == []


def test_is_due_on_open() -> None:
    t = Task(id="a", prompt="p", cadence="on-open")
    now = datetime(2026, 6, 13, 9, 0)
    assert store.is_due(t, None, now) is True
    assert store.is_due(t, now.isoformat(), now) is True  # always due


def test_is_due_daily() -> None:
    t = Task(id="a", prompt="p", cadence="daily")
    now = datetime(2026, 6, 13, 9, 0)
    assert store.is_due(t, None, now) is True  # never run
    assert store.is_due(t, datetime(2026, 6, 12, 23, 0).isoformat(), now) is True  # yesterday
    assert store.is_due(t, datetime(2026, 6, 13, 1, 0).isoformat(), now) is False  # earlier today


def test_is_due_weekly() -> None:
    t = Task(id="a", prompt="p", cadence="weekly")
    now = datetime(2026, 6, 13, 9, 0)
    assert store.is_due(t, datetime(2026, 6, 5, 9, 0).isoformat(), now) is True  # 8 days
    assert store.is_due(t, datetime(2026, 6, 10, 9, 0).isoformat(), now) is False  # 3 days


def test_disabled_never_due() -> None:
    t = Task(id="a", prompt="p", cadence="on-open", enabled=False)
    assert store.is_due(t, None, datetime(2026, 6, 13)) is False


def test_mark_run_and_due_tasks(tmp_path: Path) -> None:
    state = tmp_path / "data" / "state.json"
    daily = store.add_task(tmp_path, "daily job", "daily")
    onopen = store.add_task(tmp_path, "open job", "on-open")
    now = datetime(2026, 6, 13, 9, 0)

    due_ids = {t.id for t in store.due_tasks(tmp_path, state, now)}
    assert due_ids == {daily.id, onopen.id}  # both due (never run)

    store.mark_run(state, daily.id, now)
    due_ids = {t.id for t in store.due_tasks(tmp_path, state, now)}
    assert due_ids == {onopen.id}  # daily ran today; on-open always due
    assert store.load_state(state)[daily.id] == now.isoformat()
