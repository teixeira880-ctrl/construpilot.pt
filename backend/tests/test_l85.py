"""Lot 85 — détection d'une tâche d'import orpheline."""
from datetime import datetime, timedelta, timezone

from routes.plans_crud import _stale85


def _iso(minutes_ago):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def test_old_processing_job_is_stale():
    assert _stale85({"created_at": _iso(30), "updated_at": _iso(30)})


def test_recent_or_progressing_job_is_not_stale():
    assert not _stale85({"created_at": _iso(2), "updated_at": _iso(2)})
    assert not _stale85({"created_at": _iso(30), "updated_at": _iso(1)})   # analyse multipage qui progresse


def test_unparseable_date_is_not_stale():
    assert not _stale85({"created_at": None})
