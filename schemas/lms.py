"""Schemas del LMS SGSI."""
from __future__ import annotations

from datetime import datetime, date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PostStatus = Literal["draft", "published", "archived"]


class LMSPostBase(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    category: str = Field(min_length=3, max_length=80)
    version: str = Field(default="1.0", max_length=30)
    slug: str = Field(min_length=3, max_length=180)
    status: PostStatus = "draft"
    html_content: str = ""
    porcentaje_aprobacion: float = Field(default=80.0, ge=1, le=100)
    max_intentos: int = Field(default=3, ge=1, le=10)


class LMSPostCreate(LMSPostBase):
    pass


class LMSPostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=180)
    category: str | None = Field(default=None, min_length=3, max_length=80)
    version: str | None = Field(default=None, max_length=30)
    slug: str | None = Field(default=None, min_length=3, max_length=180)
    status: PostStatus | None = None
    html_content: str | None = None
    porcentaje_aprobacion: float | None = Field(default=None, ge=1, le=100)
    max_intentos: int | None = Field(default=None, ge=1, le=10)


class LMSPostResponse(LMSPostBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime


class LMSPeriodCreate(BaseModel):
    year: int = Field(ge=2020, le=2100)
    semester: int = Field(ge=1, le=2)
    start_date: date
    end_date: date
    name: str = Field(min_length=5, max_length=80)
    is_active: bool = False


class LMSPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    year: int
    semester: int
    start_date: date
    end_date: date
    is_active: bool
    activated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LMSQuizOptionCreate(BaseModel):
    option_order: int = Field(ge=1)
    option_text: str = Field(min_length=1)
    is_correct: bool = False


class LMSQuizQuestionCreate(BaseModel):
    question_order: int = Field(ge=1)
    statement: str = Field(min_length=5)
    weight: float = Field(default=1.0, gt=0)
    options: list[LMSQuizOptionCreate] = Field(default_factory=list, min_length=2)


class LMSQuizCreate(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    instructions: str = ""
    version: str = Field(default="1.0", max_length=30)
    is_active: bool = True
    questions: list[LMSQuizQuestionCreate] = Field(default_factory=list, min_length=1)


class LMSQuizOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    option_order: int
    option_text: str


class LMSQuizQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_order: int
    statement: str
    weight: float
    options: list[LMSQuizOptionResponse]


class LMSQuizResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: int
    title: str
    instructions: str
    version: str
    is_active: bool
    questions: list[LMSQuizQuestionResponse]


class LMSQuizAnswerInput(BaseModel):
    question_id: int
    option_id: int | None = None


class LMSAttemptSubmitRequest(BaseModel):
    answers: list[LMSQuizAnswerInput] = Field(default_factory=list)


class LMSAttemptAnswerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_id: int
    selected_option_id: int | None
    is_correct: bool


class LMSAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    post_id: int
    quiz_id: int
    period_id: int
    attempt_number: int
    total_questions: int
    correct_answers: int
    score_percentage: float
    is_passed: bool
    ip_origen: str | None
    user_agent: str | None
    version_post: str
    version_quiz: str
    started_at: datetime
    submitted_at: datetime
    created_at: datetime
    answers: list[LMSAttemptAnswerResponse]


class LMSUserPostStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    post_id: int
    period_id: int
    attempts_used: int
    max_attempts: int
    is_passed: bool
    is_blocked: bool
    passed_at: datetime | None
    blocked_at: datetime | None
    last_attempt_at: datetime | None
    updated_at: datetime
    attempts_remaining: int
    can_answer: bool
    reason: str


class LMSUserPeriodSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    period_id: int
    total_posts: int
    completed_posts: int
    approved_posts: int
    pending_posts: int
    failed_posts: int
    compliance_percentage: float
    approval_percentage: float
    avg_attempts: float
    updated_at: datetime


class LMSUserDashboardItem(BaseModel):
    post_id: int
    slug: str
    title: str
    category: str
    version: str
    status: str
    attempts_used: int
    attempts_remaining: int
    is_passed: bool
    is_blocked: bool
    can_answer: bool
    reason: str


class LMSUserDashboardResponse(BaseModel):
    user_id: int
    period: LMSPeriodResponse
    summary: LMSUserPeriodSummaryResponse
    posts: list[LMSUserDashboardItem]


class LMSPeriodMetrics(BaseModel):
    period_id: int
    total_users: int
    total_posts: int
    total_attempts: int
    total_approved_attempts: int
    cumplimiento_porcentaje: float
    aprobacion_porcentaje: float
    promedio_intentos: float
    aprobacion_primer_intento: float
    aprobacion_segundo_intento: float
    aprobacion_tercer_intento: float
    usuarios_pendientes: int


class LMSMetricPostItem(BaseModel):
    post_id: int
    slug: str
    title: str
    total_attempts: int
    approved_attempts: int
    failed_attempts: int
    approval_rate: float
    avg_attempt_number: float
    difficulty_score: float


class LMSMetricUserItem(BaseModel):
    user_id: int
    username: str
    total_posts: int
    approved_posts: int
    pending_posts: int
    compliance_percentage: float
    approval_percentage: float


class LMSComplianceItem(BaseModel):
    post_id: int
    slug: str
    title: str
    users_expected: int
    users_approved: int
    users_pending: int
    compliance_percentage: float

