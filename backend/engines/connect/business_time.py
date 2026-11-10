"""Prazos em horas úteis (seg–sex, 09:00–18:00, Europe/Lisbon). Feriados não considerados (documentado)."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Lisbon")
START, END = time(9, 0), time(18, 0)


def _next_open(dt: datetime) -> datetime:
    while True:
        if dt.weekday() >= 5:
            dt = datetime.combine(dt.date() + timedelta(days=7 - dt.weekday()), START, TZ)
            continue
        if dt.time() < START:
            return datetime.combine(dt.date(), START, TZ)
        if dt.time() >= END:
            dt = datetime.combine(dt.date() + timedelta(days=1), START, TZ)
            continue
        return dt


def add_business_hours(start: datetime, hours: float) -> datetime:
    """Devolve o instante (UTC) que fica `hours` horas úteis depois de `start`."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    remaining = timedelta(hours=max(0.0, hours))
    cur = _next_open(start.astimezone(TZ))
    while True:
        end_of_day = datetime.combine(cur.date(), END, TZ)
        available = end_of_day - cur
        if remaining <= available:
            return (cur + remaining).astimezone(timezone.utc)
        remaining -= available
        cur = _next_open(end_of_day)


def add_business_days(start: datetime, days: int) -> datetime:
    return add_business_hours(start, days * 9)
