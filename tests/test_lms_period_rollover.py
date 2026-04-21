from unittest.mock import MagicMock

from utils import lms_period_rollover


def test_ensure_lms_period_rollover_db_invokes_active_period_logic(monkeypatch):
    fake_db = MagicMock()
    expected = object()
    tracker = {"called": False}

    def _fake_get_active_period(db):
        tracker["called"] = True
        assert db is fake_db
        return expected

    monkeypatch.setattr(lms_period_rollover, "get_active_period", _fake_get_active_period)
    result = lms_period_rollover.ensure_lms_period_rollover_db(fake_db)
    assert tracker["called"] is True
    assert result is expected
