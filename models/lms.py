"""Modelos del LMS SGSI con trazabilidad y auditoría por semestre."""
from __future__ import annotations

from datetime import UTC, datetime, date

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from utils.database import Base


class LMSPost(Base):
    __tablename__ = "lms_posts"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_lms_posts_slug"),
        Index("ix_lms_posts_category_status", "category", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(30), nullable=False, default="1.0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    html_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    porcentaje_aprobacion: Mapped[float] = mapped_column(Float, nullable=False, default=80.0)
    max_intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    quizzes: Mapped[list["LMSQuiz"]] = relationship("LMSQuiz", back_populates="post")
    attempts: Mapped[list["LMSQuizAttempt"]] = relationship("LMSQuizAttempt", back_populates="post")
    user_statuses: Mapped[list["LMSUserPostStatus"]] = relationship(
        "LMSUserPostStatus", back_populates="post"
    )


class LMSPeriod(Base):
    __tablename__ = "lms_periods"
    __table_args__ = (
        UniqueConstraint("year", "semester", name="uq_lms_period_year_semester"),
        Index("ix_lms_period_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    semester: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # 1 o 2
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    attempts: Mapped[list["LMSQuizAttempt"]] = relationship("LMSQuizAttempt", back_populates="period")
    user_statuses: Mapped[list["LMSUserPostStatus"]] = relationship(
        "LMSUserPostStatus", back_populates="period"
    )
    user_summaries: Mapped[list["LMSUserPeriodSummary"]] = relationship(
        "LMSUserPeriodSummary", back_populates="period"
    )


class LMSQuiz(Base):
    __tablename__ = "lms_quizzes"
    __table_args__ = (
        UniqueConstraint("post_id", "version", name="uq_lms_quiz_post_version"),
        Index("ix_lms_quiz_post_active", "post_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("lms_posts.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[str] = mapped_column(String(30), nullable=False, default="1.0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    post: Mapped["LMSPost"] = relationship("LMSPost", back_populates="quizzes")
    questions: Mapped[list["LMSQuizQuestion"]] = relationship(
        "LMSQuizQuestion", back_populates="quiz", order_by="LMSQuizQuestion.question_order"
    )
    attempts: Mapped[list["LMSQuizAttempt"]] = relationship("LMSQuizAttempt", back_populates="quiz")


class LMSQuizQuestion(Base):
    __tablename__ = "lms_quiz_questions"
    __table_args__ = (
        Index("ix_lms_questions_quiz_order", "quiz_id", "question_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("lms_quizzes.id"), nullable=False, index=True)
    question_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    quiz: Mapped["LMSQuiz"] = relationship("LMSQuiz", back_populates="questions")
    options: Mapped[list["LMSQuizOption"]] = relationship(
        "LMSQuizOption", back_populates="question", order_by="LMSQuizOption.option_order"
    )


class LMSQuizOption(Base):
    __tablename__ = "lms_quiz_options"
    __table_args__ = (
        Index("ix_lms_options_question_order", "question_id", "option_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("lms_quiz_questions.id"), nullable=False, index=True
    )
    option_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    option_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    question: Mapped["LMSQuizQuestion"] = relationship("LMSQuizQuestion", back_populates="options")


class LMSQuizAttempt(Base):
    __tablename__ = "lms_quiz_attempts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "post_id", "period_id", "attempt_number",
            name="uq_lms_attempt_user_post_period_number",
        ),
        Index("ix_lms_attempt_user_post_period", "user_id", "post_id", "period_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("lms_posts.id"), nullable=False, index=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("lms_quizzes.id"), nullable=False, index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("lms_periods.id"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ip_origen: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version_post: Mapped[str] = mapped_column(String(30), nullable=False)
    version_quiz: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    post: Mapped["LMSPost"] = relationship("LMSPost", back_populates="attempts")
    quiz: Mapped["LMSQuiz"] = relationship("LMSQuiz", back_populates="attempts")
    period: Mapped["LMSPeriod"] = relationship("LMSPeriod", back_populates="attempts")
    answers: Mapped[list["LMSQuizAttemptAnswer"]] = relationship(
        "LMSQuizAttemptAnswer", back_populates="attempt"
    )


class LMSQuizAttemptAnswer(Base):
    __tablename__ = "lms_quiz_attempt_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_lms_attempt_answer_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("lms_quiz_attempts.id"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("lms_quiz_questions.id"), nullable=False, index=True
    )
    selected_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("lms_quiz_options.id"), nullable=True, index=True
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    attempt: Mapped["LMSQuizAttempt"] = relationship("LMSQuizAttempt", back_populates="answers")


class LMSUserPostStatus(Base):
    __tablename__ = "lms_user_post_status"
    __table_args__ = (
        UniqueConstraint("user_id", "post_id", "period_id", name="uq_lms_user_post_period"),
        Index("ix_lms_user_post_period", "user_id", "period_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("lms_posts.id"), nullable=False, index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("lms_periods.id"), nullable=False, index=True)
    attempts_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    passed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    post: Mapped["LMSPost"] = relationship("LMSPost", back_populates="user_statuses")
    period: Mapped["LMSPeriod"] = relationship("LMSPeriod", back_populates="user_statuses")


class LMSUserPeriodSummary(Base):
    __tablename__ = "lms_user_period_summary"
    __table_args__ = (
        UniqueConstraint("user_id", "period_id", name="uq_lms_user_period_summary"),
        Index("ix_lms_period_summary_period", "period_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("lms_periods.id"), nullable=False, index=True)
    total_posts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_posts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_posts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_posts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_posts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compliance_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    approval_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_attempts: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    period: Mapped["LMSPeriod"] = relationship("LMSPeriod", back_populates="user_summaries")
