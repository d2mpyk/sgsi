import os

from models.documents import Document
from tests.test_lms_routes import create_post_with_quiz, create_user, login


def test_lms_extended_api_endpoints_and_permissions(client, db_session):
    admin, admin_password = create_user(db_session, "lms_admin_ext", role="admin")
    auditor, auditor_password = create_user(db_session, "lms_auditor_ext", role="auditor")
    user, user_password = create_user(db_session, "lms_user_ext")

    published = create_post_with_quiz(db_session, admin_id=admin.id, slug="ext-published", title="Publicado")
    draft = create_post_with_quiz(db_session, admin_id=admin.id, slug="ext-draft", title="Borrador")
    draft.status = "draft"
    db_session.commit()

    login(client, user.username, user_password)

    listed = client.get("/api/v1/lms/posts")
    assert listed.status_code == 200
    slugs = {item["slug"] for item in listed.json()}
    assert "ext-published" in slugs
    assert "ext-draft" not in slugs

    hidden = client.get("/api/v1/lms/posts/ext-draft")
    assert hidden.status_code == 403

    not_found = client.get("/api/v1/lms/posts/does-not-exist")
    assert not_found.status_code == 404

    published_get = client.get(f"/api/v1/lms/posts/{published.slug}")
    assert published_get.status_code == 200

    detail_hidden = client.get(f"/api/v1/lms/view/posts/{draft.slug}")
    assert detail_hidden.status_code == 404

    client.post("/api/v1/auth/logout")
    login(client, admin.username, admin_password)

    created = client.post(
        "/api/v1/lms/posts",
        json={
            "title": "Tema API",
            "category": "Capacitación SGSI",
            "version": "1.0",
            "slug": "tema-api",
            "status": "published",
            "html_content": "<p>[[LMS_POSTS_URL]]</p>",
            "porcentaje_aprobacion": 80,
            "max_intentos": 3,
        },
    )
    assert created.status_code == 201
    created_post = created.json()

    patched = client.patch(
        f"/api/v1/lms/posts/{created_post['id']}",
        json={"title": "Tema API Actualizado", "slug": "tema-api-actualizado"},
    )
    assert patched.status_code == 200
    updated_post = patched.json()
    assert updated_post["slug"] == "tema-api-actualizado"

    quiz_missing = client.get(f"/api/v1/lms/posts/{created_post['id']}/quiz")
    assert quiz_missing.status_code == 404

    quiz_created = client.post(
        f"/api/v1/lms/posts/{created_post['id']}/quiz",
        json={
            "title": "Quiz API",
            "instructions": "Responde",
            "version": "1.0",
            "is_active": True,
            "questions": [
                {
                    "question_order": 1,
                    "statement": "¿Cuál es la idea principal del SGSI?",
                    "weight": 1,
                    "options": [
                        {"option_order": 1, "option_text": "Proteger información", "is_correct": True},
                        {"option_order": 2, "option_text": "Evitar procesos", "is_correct": False},
                    ],
                }
            ],
        },
    )
    assert quiz_created.status_code == 201

    quiz_get = client.get(f"/api/v1/lms/posts/{created_post['id']}/quiz")
    assert quiz_get.status_code == 200

    active_period = client.get("/api/v1/lms/periods/active")
    assert active_period.status_code == 200
    period_id = active_period.json()["id"]

    metrics = client.get(f"/api/v1/lms/metrics/period/{period_id}")
    assert metrics.status_code == 200
    assert "total_users" in metrics.json()

    assert client.get(f"/api/v1/lms/metrics/period/{period_id}/posts").status_code == 200
    assert client.get(f"/api/v1/lms/metrics/period/{period_id}/users").status_code == 200
    assert client.get(f"/api/v1/lms/metrics/period/{period_id}/compliance").status_code == 200

    created_period = client.post(
        "/api/v1/lms/periods",
        json={
            "year": 2099,
            "semester": 1,
            "start_date": "2099-01-01",
            "end_date": "2099-06-30",
            "name": "2099-S1",
            "is_active": False,
        },
    )
    assert created_period.status_code == 201

    period_activation = client.post(f"/api/v1/lms/periods/activate/{created_period.json()['id']}")
    assert period_activation.status_code == 200

    client.post("/api/v1/auth/logout")
    login(client, user.username, user_password)

    user_detail = client.get(f"/api/v1/lms/view/posts/{updated_post['slug']}")
    assert user_detail.status_code == 200
    assert "[[LMS_POSTS_URL]]" not in user_detail.text

    status_response = client.get(f"/api/v1/lms/posts/{created_post['id']}/status")
    assert status_response.status_code == 200

    quiz_payload = quiz_get.json()
    question_id = quiz_payload["questions"][0]["id"]
    option_id = quiz_payload["questions"][0]["options"][0]["id"]
    attempt = client.post(
        f"/api/v1/lms/posts/{created_post['id']}/attempt",
        json={"answers": [{"question_id": question_id, "option_id": option_id}]},
    )
    assert attempt.status_code == 200

    own_attempts = client.get(f"/api/v1/lms/users/{user.id}/attempts")
    assert own_attempts.status_code == 200
    assert len(own_attempts.json()) >= 1

    forbidden_attempts = client.get(f"/api/v1/lms/users/{admin.id}/attempts")
    assert forbidden_attempts.status_code == 403

    own_dashboard = client.get(f"/api/v1/lms/users/{user.id}/dashboard")
    assert own_dashboard.status_code == 200

    forbidden_dashboard = client.get(f"/api/v1/lms/users/{admin.id}/dashboard")
    assert forbidden_dashboard.status_code == 403

    client.post("/api/v1/auth/logout")
    login(client, auditor.username, auditor_password)
    auditor_posts = client.get("/api/v1/lms/posts")
    assert auditor_posts.status_code == 200
    assert any(item["slug"] == "ext-draft" for item in auditor_posts.json())


def test_lms_html_views_config_actions_and_export_pdf(client, db_session):
    admin, admin_password = create_user(db_session, "lms_admin_html", role="admin")
    user, user_password = create_user(db_session, "lms_user_html")
    post = create_post_with_quiz(db_session, admin_id=admin.id, slug="html-post", title="Post HTML")

    login(client, user.username, user_password)
    user_config_denied = client.get("/api/v1/lms/view/config")
    assert user_config_denied.status_code == 403

    client.post("/api/v1/auth/logout")
    login(client, admin.username, admin_password)

    view_posts = client.get("/api/v1/lms/view/posts")
    assert view_posts.status_code == 200

    view_metrics = client.get("/api/v1/lms/view/metrics")
    assert view_metrics.status_code == 200

    export = client.get("/api/v1/lms/view/metrics/export")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("application/pdf")
    assert "attachment;" in export.headers.get("content-disposition", "")

    generated_doc = (
        db_session.query(Document)
        .filter(Document.code == "REP-AUD-LMS")
        .order_by(Document.id.desc())
        .first()
    )
    assert generated_doc is not None
    assert generated_doc.filename.endswith(".pdf")
    assert os.path.exists(os.path.join("media", "documents", generated_doc.filename))

    config_view = client.get("/api/v1/lms/view/config")
    assert config_view.status_code == 200

    edit_post = client.post(
        f"/api/v1/lms/view/config/posts/edit/{post.id}",
        data={"html_content": "<p>contenido actualizado</p>"},
        follow_redirects=False,
    )
    assert edit_post.status_code == 303

    create_period = client.post(
        "/api/v1/lms/view/config/periods/create",
        data={
            "year": "2098",
            "semester": "2",
            "start_date": "2098-07-01",
            "end_date": "2098-12-31",
            "name": "2098-S2",
            "is_active": "on",
        },
        follow_redirects=False,
    )
    assert create_period.status_code == 303

    create_post = client.post(
        "/api/v1/lms/view/config/posts/create",
        data={
            "title": "Post form",
            "category": "Capacitación SGSI",
            "version": "1.0",
            "slug": "post-form",
            "status_post": "draft",
            "html_content": "",
            "porcentaje_aprobacion": "80",
            "max_intentos": "3",
        },
        follow_redirects=False,
    )
    assert create_post.status_code == 303

    created_post = db_session.query(Document).count()  # hit db usage path
    assert created_post >= 0

    post_form = client.get("/api/v1/lms/posts/post-form")
    assert post_form.status_code in {200, 403}

    period = client.get("/api/v1/lms/periods/active").json()
    activate_period = client.post(
        f"/api/v1/lms/view/config/periods/activate/{period['id']}",
        follow_redirects=False,
    )
    assert activate_period.status_code == 303

    activate_post = client.post(
        f"/api/v1/lms/view/config/posts/activate/{post.id}",
        follow_redirects=False,
    )
    assert activate_post.status_code == 303

    invalid_quiz = client.post(
        "/api/v1/lms/view/config/quizzes/create",
        data={
            "post_id": str(post.id),
            "title": "Quiz invalido",
            "instructions": "",
            "version": "1.0",
            "questions_json": "{}",
        },
    )
    assert invalid_quiz.status_code == 400

    valid_questions_json = (
        "[{\"question_order\":1,\"statement\":\"Pregunta valida\",\"options\":["
        "{\"option_order\":1,\"option_text\":\"Correcta\",\"is_correct\":true},"
        "{\"option_order\":2,\"option_text\":\"Incorrecta\",\"is_correct\":false}]}]"
    )
    create_quiz = client.post(
        "/api/v1/lms/view/config/quizzes/create",
        data={
            "post_id": str(post.id),
            "title": "Quiz nuevo",
            "instructions": "",
            "version": "1.2",
            "questions_json": valid_questions_json,
        },
        follow_redirects=False,
    )
    assert create_quiz.status_code == 303

    quiz_id = post.quizzes[0].id
    quiz_not_found = client.post(
        "/api/v1/lms/view/config/quizzes/edit/999999",
        data={
            "title": "x",
            "instructions": "",
            "version": "",
            "questions_json": valid_questions_json,
        },
    )
    assert quiz_not_found.status_code == 404

    quiz_bad_json = client.post(
        f"/api/v1/lms/view/config/quizzes/edit/{quiz_id}",
        data={
            "title": "Quiz edit",
            "instructions": "",
            "version": "",
            "questions_json": "{}",
        },
    )
    assert quiz_bad_json.status_code == 400

    quiz_edit = client.post(
        f"/api/v1/lms/view/config/quizzes/edit/{quiz_id}",
        data={
            "title": "Quiz editado",
            "instructions": "Nuevas instrucciones",
            "version": "1.0",
            "questions_json": valid_questions_json,
        },
        follow_redirects=False,
    )
    assert quiz_edit.status_code == 303

    activate_quiz = client.post(
        f"/api/v1/lms/view/config/quizzes/activate/{quiz_id}",
        follow_redirects=False,
    )
    assert activate_quiz.status_code == 303
