from datetime import datetime

from app.main import next_refresh_at, scheduler_now, seconds_until_next_refresh


SCHEDULE = ["07:00", "09:00", "12:00", "18:00", "20:00", "22:00"]


def test_next_refresh_uses_same_day_server_time():
    now = datetime(2026, 6, 27, 8, 15, 0)

    assert next_refresh_at(now, SCHEDULE) == datetime(2026, 6, 27, 9, 0, 0)


def test_next_refresh_rolls_to_next_morning_after_last_slot():
    now = datetime(2026, 6, 27, 22, 1, 0)

    assert next_refresh_at(now, SCHEDULE) == datetime(2026, 6, 28, 7, 0, 0)


def test_seconds_until_next_refresh():
    now = datetime(2026, 6, 27, 11, 30, 0)

    assert seconds_until_next_refresh(now, SCHEDULE) == 1800


def test_scheduler_now_uses_configured_timezone():
    now = scheduler_now()

    assert now.tzinfo is not None
    assert now.utcoffset() is not None
