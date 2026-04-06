from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.documents import Document, DocumentRead
from models.users import User


class DashboardStatsCache:
    def __init__(self, ttl_seconds: int = 120):
        self.ttl = ttl_seconds
        self.last_updated = None
        self.data = {
            "total_users": 0,
            "total_clients": 0,
            "total_documents": 0,
            "total_pending": 0,
            "total_errors": 0,
        }

    def get_stats(self, db: Session, current_user: User | None = None):
        now = datetime.now(UTC)
        # Si no hay datos o el tiempo de vida expiró, actualizamos desde la DB
        if self.last_updated is None or (now - self.last_updated) > timedelta(
            seconds=self.ttl
        ):
            self.data["total_users"] = (
                db.execute(select(func.count(User.id))).scalar() or 0
            )
            self.data["total_documents"] = (
                db.execute(select(func.count(Document.id))).scalar() or 0
            )

            self.last_updated = now

        stats = self.data.copy()

        if isinstance(current_user, User):
            total_active_policies = (
                db.execute(
                    select(func.count(Document.id)).where(
                        Document.doc_type == "policy",
                        Document.is_active == True,
                    )
                ).scalar()
                or 0
            )
            confirmed_reads = (
                db.execute(
                    select(func.count(DocumentRead.id)).where(
                        DocumentRead.user_id == current_user.id,
                        DocumentRead.read_at.is_not(None),
                    )
                ).scalar()
                or 0
            )
            stats["total_pending"] = max(total_active_policies - confirmed_reads, 0)

        return stats


# Instancia global para mantener el estado en memoria mientras la app corre
stats_cache = DashboardStatsCache(ttl_seconds=60)


def get_dashboard_stats(db: Session, current_user: User | None = None):
    """Obtiene estadísticas del dashboard cacheadas."""
    return stats_cache.get_stats(db, current_user=current_user)
