"""Repositorio SQLAlchemy para LMS SGSI."""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session, joinedload

from models.lms import (
    LMSPeriod,
    LMSPost,
    LMSQuiz,
    LMSQuizAttempt,
    LMSQuizAttemptAnswer,
    LMSQuizOption,
    LMSQuizQuestion,
    LMSUserPeriodSummary,
    LMSUserPostStatus,
)
from models.users import User


class LMSRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_posts(self) -> list[LMSPost]:
        return (
            self.db.execute(select(LMSPost).order_by(LMSPost.created_at.desc()))
            .scalars()
            .all()
        )

    def list_published_posts(self) -> list[LMSPost]:
        return (
            self.db.execute(
                select(LMSPost)
                .where(LMSPost.status == "published")
                .order_by(LMSPost.category.asc(), LMSPost.title.asc())
            )
            .scalars()
            .all()
        )

    def get_post_by_id(self, post_id: int) -> LMSPost | None:
        return self.db.get(LMSPost, post_id)

    def get_post_by_slug(self, slug: str) -> LMSPost | None:
        return (
            self.db.execute(select(LMSPost).where(LMSPost.slug == slug))
            .scalars()
            .first()
        )

    def create_post(self, post: LMSPost) -> LMSPost:
        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)
        return post

    def save_post(self, post: LMSPost) -> LMSPost:
        post.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(post)
        return post

    def get_active_period(self) -> LMSPeriod | None:
        return (
            self.db.execute(select(LMSPeriod).where(LMSPeriod.is_active == True))
            .scalars()
            .first()
        )

    def get_period(self, period_id: int) -> LMSPeriod | None:
        return self.db.get(LMSPeriod, period_id)

    def list_periods(self) -> list[LMSPeriod]:
        return (
            self.db.execute(
                select(LMSPeriod).order_by(LMSPeriod.year.desc(), LMSPeriod.semester.desc())
            )
            .scalars()
            .all()
        )

    def get_period_by_year_semester(self, year: int, semester: int) -> LMSPeriod | None:
        return (
            self.db.execute(
                select(LMSPeriod).where(
                    LMSPeriod.year == year,
                    LMSPeriod.semester == semester,
                )
            )
            .scalars()
            .first()
        )

    def create_period(self, period: LMSPeriod) -> LMSPeriod:
        self.db.add(period)
        self.db.commit()
        self.db.refresh(period)
        return period

    def deactivate_periods(self) -> None:
        self.db.execute(update(LMSPeriod).values(is_active=False))
        self.db.commit()

    def activate_period(self, period: LMSPeriod) -> LMSPeriod:
        self.db.execute(update(LMSPeriod).values(is_active=False))
        period.is_active = True
        period.activated_at = datetime.now(UTC)
        period.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(period)
        return period

    def get_active_quiz_for_post(self, post_id: int) -> LMSQuiz | None:
        return (
            self.db.execute(
                select(LMSQuiz)
                .options(
                    joinedload(LMSQuiz.questions).joinedload(LMSQuizQuestion.options),
                )
                .where(LMSQuiz.post_id == post_id, LMSQuiz.is_active == True)
                .order_by(LMSQuiz.id.desc())
            )
            .scalars()
            .first()
        )

    def get_quiz_by_id(self, quiz_id: int) -> LMSQuiz | None:
        return self.db.get(LMSQuiz, quiz_id)

    def list_quizzes(self) -> list[LMSQuiz]:
        return (
            self.db.execute(select(LMSQuiz).order_by(LMSQuiz.created_at.desc()))
            .scalars()
            .all()
        )

    def create_quiz(self, quiz: LMSQuiz) -> LMSQuiz:
        self.db.add(quiz)
        self.db.commit()
        self.db.refresh(quiz)
        return quiz

    def deactivate_quizzes_for_post(self, post_id: int) -> None:
        self.db.execute(
            update(LMSQuiz)
            .where(LMSQuiz.post_id == post_id, LMSQuiz.is_active == True)
            .values(is_active=False, updated_at=datetime.now(UTC))
        )
        self.db.commit()

    def activate_quiz(self, quiz: LMSQuiz) -> LMSQuiz:
        self.deactivate_quizzes_for_post(post_id=quiz.post_id)
        quiz.is_active = True
        quiz.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(quiz)
        return quiz

    def count_attempts(self, user_id: int, post_id: int, period_id: int) -> int:
        return (
            self.db.execute(
                select(func.count(LMSQuizAttempt.id)).where(
                    LMSQuizAttempt.user_id == user_id,
                    LMSQuizAttempt.post_id == post_id,
                    LMSQuizAttempt.period_id == period_id,
                )
            )
            .scalar_one()
        )

    def list_attempts_user_post_period(
        self, user_id: int, post_id: int, period_id: int
    ) -> list[LMSQuizAttempt]:
        result = self.db.execute(
            select(LMSQuizAttempt)
            .options(joinedload(LMSQuizAttempt.answers))
            .where(
                LMSQuizAttempt.user_id == user_id,
                LMSQuizAttempt.post_id == post_id,
                LMSQuizAttempt.period_id == period_id,
            )
            .order_by(LMSQuizAttempt.attempt_number.asc())
        )
        return result.unique().scalars().all()

    def create_attempt(
        self,
        attempt: LMSQuizAttempt,
        answers: list[LMSQuizAttemptAnswer],
    ) -> LMSQuizAttempt:
        self.db.add(attempt)
        self.db.flush()
        for answer in answers:
            answer.attempt_id = attempt.id
            self.db.add(answer)
        self.db.commit()
        self.db.refresh(attempt)
        attempt = (
            self.db.execute(
                select(LMSQuizAttempt)
                .options(joinedload(LMSQuizAttempt.answers))
                .where(LMSQuizAttempt.id == attempt.id)
            )
            .scalars()
            .first()
        )
        return attempt

    def get_user_post_status(
        self, user_id: int, post_id: int, period_id: int
    ) -> LMSUserPostStatus | None:
        return (
            self.db.execute(
                select(LMSUserPostStatus).where(
                    LMSUserPostStatus.user_id == user_id,
                    LMSUserPostStatus.post_id == post_id,
                    LMSUserPostStatus.period_id == period_id,
                )
            )
            .scalars()
            .first()
        )

    def save_user_post_status(self, status_row: LMSUserPostStatus) -> LMSUserPostStatus:
        if status_row.id is None:
            self.db.add(status_row)
        status_row.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(status_row)
        return status_row

    def get_user_period_summary(self, user_id: int, period_id: int) -> LMSUserPeriodSummary | None:
        return (
            self.db.execute(
                select(LMSUserPeriodSummary).where(
                    LMSUserPeriodSummary.user_id == user_id,
                    LMSUserPeriodSummary.period_id == period_id,
                )
            )
            .scalars()
            .first()
        )

    def save_user_period_summary(self, summary: LMSUserPeriodSummary) -> LMSUserPeriodSummary:
        if summary.id is None:
            self.db.add(summary)
        summary.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(summary)
        return summary

    def list_users(self) -> list[User]:
        return self.db.execute(select(User).where(User.is_active == True)).scalars().all()

    def list_attempts_by_user(self, user_id: int) -> list[LMSQuizAttempt]:
        result = self.db.execute(
            select(LMSQuizAttempt)
            .options(joinedload(LMSQuizAttempt.answers))
            .where(LMSQuizAttempt.user_id == user_id)
            .order_by(LMSQuizAttempt.submitted_at.desc())
        )
        return result.unique().scalars().all()

    def list_period_posts(self, period_id: int) -> list[LMSQuizAttempt]:
        return (
            self.db.execute(
                select(LMSQuizAttempt).where(LMSQuizAttempt.period_id == period_id)
            )
            .scalars()
            .all()
        )

    def list_statuses_for_period(self, period_id: int) -> list[LMSUserPostStatus]:
        return (
            self.db.execute(
                select(LMSUserPostStatus).where(LMSUserPostStatus.period_id == period_id)
            )
            .scalars()
            .all()
        )

    def list_user_summaries_for_period(self, period_id: int) -> list[LMSUserPeriodSummary]:
        return (
            self.db.execute(
                select(LMSUserPeriodSummary).where(LMSUserPeriodSummary.period_id == period_id)
            )
            .scalars()
            .all()
        )

    def list_posts_by_ids(self, post_ids: list[int]) -> list[LMSPost]:
        if not post_ids:
            return []
        return (
            self.db.execute(select(LMSPost).where(LMSPost.id.in_(post_ids)))
            .scalars()
            .all()
        )
