from fastapi.responses import RedirectResponse

from utils.stats import get_dashboard_stats, stats_cache


def test_get_dashboard_stats_ignores_redirect_response_as_current_user(db_session):
    stats_cache.last_updated = None

    redirect_user = RedirectResponse(url="/api/v1/auth/login", status_code=303)
    stats = get_dashboard_stats(db_session, current_user=redirect_user)  # type: ignore[arg-type]

    assert isinstance(stats, dict)
    assert "total_users" in stats
    assert "total_documents" in stats
    assert stats["total_pending"] == 0
