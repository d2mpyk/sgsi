"""create lms tables

Revision ID: 20260421_0001
Revises:
Create Date: 2026-04-21 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260421_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lms_posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("version", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("html_content", sa.Text(), nullable=False),
        sa.Column("porcentaje_aprobacion", sa.Float(), nullable=False),
        sa.Column("max_intentos", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_lms_posts_slug"),
    )
    op.create_index("ix_lms_posts_slug", "lms_posts", ["slug"])
    op.create_index("ix_lms_posts_status", "lms_posts", ["status"])
    op.create_index("ix_lms_posts_category_status", "lms_posts", ["category", "status"])

    op.create_table(
        "lms_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("year", "semester", name="uq_lms_period_year_semester"),
    )
    op.create_index("ix_lms_period_active", "lms_periods", ["is_active"])
    op.create_index("ix_lms_periods_year", "lms_periods", ["year"])
    op.create_index("ix_lms_periods_semester", "lms_periods", ["semester"])

    op.create_table(
        "lms_quizzes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["lms_posts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "version", name="uq_lms_quiz_post_version"),
    )
    op.create_index("ix_lms_quiz_post_active", "lms_quizzes", ["post_id", "is_active"])

    op.create_table(
        "lms_quiz_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quiz_id", sa.Integer(), nullable=False),
        sa.Column("question_order", sa.Integer(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["quiz_id"], ["lms_quizzes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lms_questions_quiz_order", "lms_quiz_questions", ["quiz_id", "question_order"])

    op.create_table(
        "lms_quiz_options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("option_order", sa.Integer(), nullable=False),
        sa.Column("option_text", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["lms_quiz_questions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lms_options_question_order", "lms_quiz_options", ["question_id", "option_order"])

    op.create_table(
        "lms_quiz_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("quiz_id", sa.Integer(), nullable=False),
        sa.Column("period_id", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("correct_answers", sa.Integer(), nullable=False),
        sa.Column("score_percentage", sa.Float(), nullable=False),
        sa.Column("is_passed", sa.Boolean(), nullable=False),
        sa.Column("ip_origen", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("version_post", sa.String(length=30), nullable=False),
        sa.Column("version_quiz", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["period_id"], ["lms_periods.id"]),
        sa.ForeignKeyConstraint(["post_id"], ["lms_posts.id"]),
        sa.ForeignKeyConstraint(["quiz_id"], ["lms_quizzes.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "post_id", "period_id", "attempt_number",
            name="uq_lms_attempt_user_post_period_number",
        ),
    )
    op.create_index(
        "ix_lms_attempt_user_post_period",
        "lms_quiz_attempts",
        ["user_id", "post_id", "period_id"],
    )

    op.create_table(
        "lms_quiz_attempt_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("selected_option_id", sa.Integer(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["lms_quiz_attempts.id"]),
        sa.ForeignKeyConstraint(["question_id"], ["lms_quiz_questions.id"]),
        sa.ForeignKeyConstraint(["selected_option_id"], ["lms_quiz_options.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_lms_attempt_answer_question"),
    )

    op.create_table(
        "lms_user_post_status",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("period_id", sa.Integer(), nullable=False),
        sa.Column("attempts_used", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("is_passed", sa.Boolean(), nullable=False),
        sa.Column("is_blocked", sa.Boolean(), nullable=False),
        sa.Column("passed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["period_id"], ["lms_periods.id"]),
        sa.ForeignKeyConstraint(["post_id"], ["lms_posts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "post_id", "period_id", name="uq_lms_user_post_period"),
    )
    op.create_index("ix_lms_user_post_period", "lms_user_post_status", ["user_id", "period_id"])

    op.create_table(
        "lms_user_period_summary",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("period_id", sa.Integer(), nullable=False),
        sa.Column("total_posts", sa.Integer(), nullable=False),
        sa.Column("completed_posts", sa.Integer(), nullable=False),
        sa.Column("approved_posts", sa.Integer(), nullable=False),
        sa.Column("pending_posts", sa.Integer(), nullable=False),
        sa.Column("failed_posts", sa.Integer(), nullable=False),
        sa.Column("compliance_percentage", sa.Float(), nullable=False),
        sa.Column("approval_percentage", sa.Float(), nullable=False),
        sa.Column("avg_attempts", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["period_id"], ["lms_periods.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "period_id", name="uq_lms_user_period_summary"),
    )
    op.create_index("ix_lms_period_summary_period", "lms_user_period_summary", ["period_id"])


def downgrade() -> None:
    op.drop_index("ix_lms_period_summary_period", table_name="lms_user_period_summary")
    op.drop_table("lms_user_period_summary")
    op.drop_index("ix_lms_user_post_period", table_name="lms_user_post_status")
    op.drop_table("lms_user_post_status")
    op.drop_table("lms_quiz_attempt_answers")
    op.drop_index("ix_lms_attempt_user_post_period", table_name="lms_quiz_attempts")
    op.drop_table("lms_quiz_attempts")
    op.drop_index("ix_lms_options_question_order", table_name="lms_quiz_options")
    op.drop_table("lms_quiz_options")
    op.drop_index("ix_lms_questions_quiz_order", table_name="lms_quiz_questions")
    op.drop_table("lms_quiz_questions")
    op.drop_index("ix_lms_quiz_post_active", table_name="lms_quizzes")
    op.drop_table("lms_quizzes")
    op.drop_index("ix_lms_periods_semester", table_name="lms_periods")
    op.drop_index("ix_lms_periods_year", table_name="lms_periods")
    op.drop_index("ix_lms_period_active", table_name="lms_periods")
    op.drop_table("lms_periods")
    op.drop_index("ix_lms_posts_category_status", table_name="lms_posts")
    op.drop_index("ix_lms_posts_status", table_name="lms_posts")
    op.drop_index("ix_lms_posts_slug", table_name="lms_posts")
    op.drop_table("lms_posts")
