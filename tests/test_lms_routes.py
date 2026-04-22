from models.departments import Department
from models.lms import LMSPost, LMSQuiz, LMSQuizOption, LMSQuizQuestion
from models.users import User
from unittest.mock import mock_open, patch
from utils.auth import hash_password


def get_department_id(db_session, name: str = "Infraestructura") -> int:
    department = (
        db_session.query(Department)
        .filter(Department.departamento == name)
        .first()
    )
    assert department is not None
    return department.id


def login(client, username: str, password: str):
    response = client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200


def create_user(db_session, username: str, role: str = "user", password: str = "Pass1234!"):
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password(password),
        role=role,
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user, password


def create_post_with_quiz(db_session, admin_id: int, slug: str, title: str = "Tema LMS", passing: float = 80.0):
    post = LMSPost(
        title=title,
        slug=slug,
        category="Capacitación SGSI",
        version="1.0",
        status="published",
        html_content="",
        porcentaje_aprobacion=passing,
        max_intentos=3,
        created_by_id=admin_id,
    )
    quiz = LMSQuiz(
        title=f"Quiz {title}",
        instructions="Selecciona la opción correcta",
        version="1.0",
        is_active=True,
    )
    question = LMSQuizQuestion(question_order=1, statement="¿Respuesta correcta?", weight=1.0, is_active=True)
    question.options.append(LMSQuizOption(option_order=1, option_text="Correcta", is_correct=True))
    question.options.append(LMSQuizOption(option_order=2, option_text="Incorrecta", is_correct=False))
    quiz.questions.append(question)
    post.quizzes.append(quiz)
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)
    return post


def test_lms_get_posts_returns_published_posts_for_user(client, db_session):
    admin, _ = create_user(db_session, "lms_admin", role="admin")
    user, password = create_user(db_session, "lms_user")
    create_post_with_quiz(db_session, admin_id=admin.id, slug="fundamentos-sgsi", title="Fundamentos")

    login(client, user.username, password)
    response = client.get("/api/v1/lms/posts")

    assert response.status_code == 200
    assert any(item["slug"] == "fundamentos-sgsi" for item in response.json())


def test_lms_config_button_and_view_are_admin_only(client, db_session):
    admin, admin_password = create_user(db_session, "lms_admin_cfg", role="admin")
    user, user_password = create_user(db_session, "lms_user_cfg")

    login(client, admin.username, admin_password)
    page = client.get("/api/v1/lms/view/posts")
    assert page.status_code == 200
    assert "Configuración" in page.text

    admin_view = client.get("/api/v1/lms/view/config")
    assert admin_view.status_code == 200
    assert "Configuración LMS SGSI" in admin_view.text

    client.post("/api/v1/auth/logout")
    login(client, user.username, user_password)
    user_page = client.get("/api/v1/lms/view/posts")
    assert user_page.status_code == 200
    assert "Configuración" not in user_page.text

    denied = client.get("/api/v1/lms/view/config")
    assert denied.status_code == 403


def test_lms_attempt_is_blocked_after_three_failed_attempts(client, db_session):
    admin, _ = create_user(db_session, "lms_admin_2", role="admin")
    user, password = create_user(db_session, "lms_user_2")
    post = create_post_with_quiz(db_session, admin_id=admin.id, slug="riesgos-sgsi", title="Riesgos")
    wrong_option = post.quizzes[0].questions[0].options[1]

    login(client, user.username, password)
    for _ in range(3):
        response = client.post(
            f"/api/v1/lms/posts/{post.id}/attempt",
            json={"answers": [{"question_id": post.quizzes[0].questions[0].id, "option_id": wrong_option.id}]},
        )
        assert response.status_code == 200
        assert response.json()["is_passed"] is False

    blocked = client.post(
        f"/api/v1/lms/posts/{post.id}/attempt",
        json={"answers": [{"question_id": post.quizzes[0].questions[0].id, "option_id": wrong_option.id}]},
    )
    assert blocked.status_code == 409
    assert "Intentos agotados" in blocked.json()["detail"]


def test_lms_passed_attempt_blocks_remaining_attempts(client, db_session):
    admin, _ = create_user(db_session, "lms_admin_3", role="admin")
    user, password = create_user(db_session, "lms_user_3")
    post = create_post_with_quiz(
        db_session,
        admin_id=admin.id,
        slug="cumplimiento-auditoria",
        title="Cumplimiento y Auditoría",
        passing=50.0,
    )
    correct_option = post.quizzes[0].questions[0].options[0]

    login(client, user.username, password)
    mocked_open = mock_open()
    with patch("services.lms_service.os.makedirs"), patch("services.lms_service.open", mocked_open):
        passed = client.post(
            f"/api/v1/lms/posts/{post.id}/attempt",
            json={"answers": [{"question_id": post.quizzes[0].questions[0].id, "option_id": correct_option.id}]},
        )
    assert passed.status_code == 200
    payload = passed.json()
    assert payload["is_passed"] is True
    assert payload["ip_origen"] is not None
    assert payload["version_post"] == "1.0"
    assert payload["version_quiz"] == "1.0"
    assert payload["certificate_filename"].endswith(".pdf")
    assert "/media/documents/certificates/" in payload["certificate_url"]

    blocked = client.post(
        f"/api/v1/lms/posts/{post.id}/attempt",
        json={"answers": [{"question_id": post.quizzes[0].questions[0].id, "option_id": correct_option.id}]},
    )
    assert blocked.status_code == 409
    assert "Ya aprobaste" in blocked.json()["detail"]


def test_lms_post_html_replaces_lms_posts_url_token(client, db_session):
    admin, _ = create_user(db_session, "lms_admin_token", role="admin")
    user, password = create_user(db_session, "lms_user_token")
    post = create_post_with_quiz(
        db_session,
        admin_id=admin.id,
        slug="fundamentos-token",
        title="Fundamentos token",
    )
    post.html_content = '<a id="go-lms" href="[[LMS_POSTS_URL]]">Capacitación SGSI</a>'
    db_session.commit()

    login(client, user.username, password)
    response = client.get(f"/api/v1/lms/view/posts/{post.slug}")

    assert response.status_code == 200
    assert 'id="go-lms"' in response.text
    assert "/lms/view/posts" in response.text
    assert "[[LMS_POSTS_URL]]" not in response.text


def test_lms_post_html_replaces_legacy_jinja_url_for_literal(client, db_session):
    admin, _ = create_user(db_session, "lms_admin_jinja", role="admin")
    user, password = create_user(db_session, "lms_user_jinja")
    post = create_post_with_quiz(
        db_session,
        admin_id=admin.id,
        slug="fundamentos-jinja",
        title="Fundamentos jinja",
    )
    post.html_content = '<a id="go-jinja" href="{{ url_for(\'lms_posts_view\') }}">Capacitación SGSI</a>'
    db_session.commit()

    login(client, user.username, password)
    response = client.get(f"/api/v1/lms/view/posts/{post.slug}")

    assert response.status_code == 200
    assert 'id="go-jinja"' in response.text
    assert "/lms/view/posts" in response.text
    assert "url_for('lms_posts_view')" not in response.text
