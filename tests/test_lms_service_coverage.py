from datetime import date

import pytest
from unittest.mock import mock_open, patch
from fastapi import HTTPException

from models.lms import LMSPeriod, LMSPost, LMSQuiz, LMSQuizOption, LMSQuizQuestion, LMSUserPostStatus
from schemas.lms import LMSAttemptSubmitRequest, LMSPostCreate, LMSPostUpdate
from services import lms_service
from tests.test_lms_routes import create_post_with_quiz, create_user


def test_slugify_and_semester_bounds_helpers():
    assert lms_service._slugify("  CÓDIGO Ñ Ü  ") == "codigo-n-u"

    year, semester, start_date, end_date, name = lms_service._get_semester_bounds(date(2026, 2, 1))
    assert (year, semester, start_date, end_date, name) == (
        2026,
        1,
        date(2026, 1, 1),
        date(2026, 6, 30),
        "2026-S1",
    )

    year, semester, start_date, end_date, name = lms_service._get_semester_bounds(date(2026, 8, 1))
    assert (year, semester, start_date, end_date, name) == (
        2026,
        2,
        date(2026, 7, 1),
        date(2026, 12, 31),
        "2026-S2",
    )


def test_get_active_period_create_and_reactivate(db_session, monkeypatch):
    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 8, 5)

    monkeypatch.setattr(lms_service, "date", FakeDate)

    created = lms_service.get_active_period(db_session)
    assert created.year == 2026
    assert created.semester == 2
    assert created.is_active is True

    another = LMSPeriod(
        name="2026-S1",
        year=2026,
        semester=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
        is_active=True,
    )
    created.is_active = False
    db_session.add(another)
    db_session.commit()

    period = lms_service.get_active_period(db_session)
    assert period.id == created.id
    assert period.is_active is True


def test_create_and_update_post_conflicts(db_session):
    admin, _ = create_user(db_session, "svc_admin", role="admin")

    created = lms_service.create_post(
        db=db_session,
        payload=LMSPostCreate(
            title="Tema Uno",
            category="Capacitación SGSI",
            version="1.0",
            slug="tema-uno",
            status="published",
            html_content="",
            porcentaje_aprobacion=80,
            max_intentos=3,
        ),
        created_by_id=admin.id,
    )
    assert created.slug == "tema-uno"

    with pytest.raises(HTTPException) as exc:
        lms_service.create_post(
            db=db_session,
            payload=LMSPostCreate(
                title="Tema Uno 2",
                category="Capacitación SGSI",
                version="1.0",
                slug="tema-uno",
                status="published",
                html_content="",
                porcentaje_aprobacion=80,
                max_intentos=3,
            ),
            created_by_id=admin.id,
        )
    assert exc.value.status_code == 409

    with pytest.raises(HTTPException) as exc_not_found:
        lms_service.update_post(db=db_session, post_id=99999, payload=LMSPostUpdate(title="Xxx"))
    assert exc_not_found.value.status_code == 404

    second = lms_service.create_post(
        db=db_session,
        payload=LMSPostCreate(
            title="Tema Dos",
            category="Capacitación SGSI",
            version="1.0",
            slug="tema-dos",
            status="published",
            html_content="",
            porcentaje_aprobacion=80,
            max_intentos=3,
        ),
        created_by_id=admin.id,
    )

    with pytest.raises(HTTPException) as exc_conflict:
        lms_service.update_post(db=db_session, post_id=second.id, payload=LMSPostUpdate(slug="tema-uno"))
    assert exc_conflict.value.status_code == 409


def test_can_user_answer_and_grade_quiz_branching(db_session):
    admin, _ = create_user(db_session, "svc_admin_state", role="admin")
    user, _ = create_user(db_session, "svc_user_state")
    post = create_post_with_quiz(db_session, admin.id, slug="svc-can-answer")
    period = lms_service.get_active_period(db_session)

    allowed = lms_service.can_user_answer_post(db=db_session, user_id=user.id, post=post, period=period)
    assert allowed.can_answer is True

    status_row = LMSUserPostStatus(
        user_id=user.id,
        post_id=post.id,
        period_id=period.id,
        attempts_used=1,
        max_attempts=3,
        is_passed=True,
        is_blocked=False,
    )
    db_session.add(status_row)
    db_session.commit()
    passed = lms_service.can_user_answer_post(db=db_session, user_id=user.id, post=post, period=period)
    assert passed.can_answer is False
    assert "Ya aprobaste" in passed.reason

    status_row.is_passed = False
    status_row.is_blocked = True
    status_row.attempts_used = 3
    db_session.commit()
    blocked = lms_service.can_user_answer_post(db=db_session, user_id=user.id, post=post, period=period)
    assert blocked.can_answer is False
    assert blocked.attempts_remaining == 0

    quiz = post.quizzes[0]
    quiz.questions[0].is_active = False
    db_session.commit()
    correct, total, score, answers = lms_service.grade_quiz(quiz=quiz, answers={})
    assert (correct, total, score, answers) == (0, 0, 0.0, [])

    quiz.questions[0].is_active = True
    db_session.commit()
    right_option = quiz.questions[0].options[0]
    correct, total, score, answers = lms_service.grade_quiz(
        quiz=quiz,
        answers={quiz.questions[0].id: right_option.id},
    )
    assert (correct, total, score) == (1, 1, 100.0)
    assert len(answers) == 1


def test_submit_attempt_and_dashboard_metrics_errors(db_session):
    admin, _ = create_user(db_session, "svc_admin_submit", role="admin")
    user, _ = create_user(db_session, "svc_user_submit")

    with pytest.raises(HTTPException) as missing_post_exc:
        lms_service.submit_quiz_attempt(
            db=db_session,
            user=user,
            post_id=99999,
            payload=LMSAttemptSubmitRequest(answers=[]),
            ip_origen="127.0.0.1",
            user_agent="pytest",
        )
    assert missing_post_exc.value.status_code == 404

    draft_post = LMSPost(
        title="Draft",
        slug="draft-post",
        category="Capacitación SGSI",
        version="1.0",
        status="draft",
        html_content="",
        porcentaje_aprobacion=80,
        max_intentos=3,
        created_by_id=admin.id,
    )
    db_session.add(draft_post)
    db_session.commit()

    with pytest.raises(HTTPException) as draft_exc:
        lms_service.submit_quiz_attempt(
            db=db_session,
            user=user,
            post_id=draft_post.id,
            payload=LMSAttemptSubmitRequest(answers=[]),
            ip_origen="127.0.0.1",
            user_agent="pytest",
        )
    assert draft_exc.value.status_code == 400

    post_no_quiz = LMSPost(
        title="No quiz",
        slug="post-no-quiz",
        category="Capacitación SGSI",
        version="1.0",
        status="published",
        html_content="",
        porcentaje_aprobacion=80,
        max_intentos=3,
        created_by_id=admin.id,
    )
    db_session.add(post_no_quiz)
    db_session.commit()

    with pytest.raises(HTTPException) as no_quiz_exc:
        lms_service.submit_quiz_attempt(
            db=db_session,
            user=user,
            post_id=post_no_quiz.id,
            payload=LMSAttemptSubmitRequest(answers=[]),
            ip_origen="127.0.0.1",
            user_agent="pytest",
        )
    assert no_quiz_exc.value.status_code == 404

    post = create_post_with_quiz(db_session, admin.id, slug="svc-submit-ok", passing=50.0)
    question = post.quizzes[0].questions[0]
    correct_option = question.options[0]

    mocked_open = mock_open()
    with patch("services.lms_service.os.makedirs"), patch("services.lms_service.open", mocked_open):
        attempt = lms_service.submit_quiz_attempt(
            db=db_session,
            user=user,
            post_id=post.id,
            payload=LMSAttemptSubmitRequest(
                answers=[{"question_id": question.id, "option_id": correct_option.id}]
            ),
            ip_origen="127.0.0.1",
            user_agent="pytest",
        )
    assert attempt.is_passed is True
    assert attempt.attempt_number == 1
    assert getattr(attempt, "certificate_filename", "").endswith(".pdf")
    assert "documents/certificates/" in getattr(attempt, "certificate_relative_path", "")

    dashboard = lms_service.dashboard_by_user(db=db_session, user_id=user.id)
    assert dashboard["summary"].approved_posts >= 1

    with pytest.raises(HTTPException) as missing_user_exc:
        lms_service.dashboard_by_user(db=db_session, user_id=99999)
    assert missing_user_exc.value.status_code == 404

    period = lms_service.get_active_period(db_session)
    metrics = lms_service.metrics_by_period(db=db_session, period_id=period.id)
    assert "kpis" in metrics
    assert isinstance(lms_service.metrics_posts_by_period(db=db_session, period_id=period.id), list)
    assert isinstance(lms_service.metrics_users_by_period(db=db_session, period_id=period.id), list)
    assert isinstance(lms_service.compliance_by_period(db=db_session, period_id=period.id), list)

    with pytest.raises(HTTPException) as missing_period_metrics:
        lms_service.metrics_by_period(db=db_session, period_id=99999)
    assert missing_period_metrics.value.status_code == 404

    with pytest.raises(HTTPException) as missing_period_compliance:
        lms_service.compliance_by_period(db=db_session, period_id=99999)
    assert missing_period_compliance.value.status_code == 404
