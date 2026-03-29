from models.suggestions import Suggestion
from models.users import User
from utils.auth import hash_password


def test_user_can_create_and_view_own_suggestions(client, db_session):
    password = "UserPass123!"
    user = User(
        username="suggest.user",
        email="suggest.user@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "suggest.user", "password": password},
    )
    assert login_response.status_code == 200

    response = client.post(
        "/api/v1/suggestions/create",
        data={"suggestion": "Sería útil tener filtros avanzados para encontrar políticas por código."},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/api/v1/suggestions/view")

    saved_suggestion = db_session.query(Suggestion).filter_by(id_user=user.id).first()
    assert saved_suggestion is not None
    assert "filtros avanzados" in saved_suggestion.suggestion

    page = client.get("/api/v1/suggestions/view")
    assert page.status_code == 200
    assert "Mis sugerencias para la aplicación" in page.text
    assert "filtros avanzados" in page.text
    assert "Sugerencias" in page.text


def test_suggestions_view_only_lists_current_user_suggestions(client, db_session):
    password = "UserPass123!"
    current_user = User(
        username="current.suggest",
        email="current.suggest@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    other_user = User(
        username="other.suggest",
        email="other.suggest@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    db_session.add_all([current_user, other_user])
    db_session.commit()

    db_session.add(
        Suggestion(
            id_user=current_user.id,
            suggestion="Mi sugerencia visible",
        )
    )
    db_session.add(
        Suggestion(
            id_user=other_user.id,
            suggestion="Sugerencia ajena no visible",
        )
    )
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "current.suggest", "password": password},
    )
    assert login_response.status_code == 200

    page = client.get("/api/v1/suggestions/view")
    assert page.status_code == 200
    assert "Mi sugerencia visible" in page.text
    assert "Sugerencia ajena no visible" not in page.text


def test_admin_suggestions_view_lists_all_users_suggestions(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="admin.suggest",
        email="admin.suggest@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    user_one = User(
        username="first.user",
        email="first.user@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    user_two = User(
        username="second.user",
        email="second.user@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add_all([admin, user_one, user_two])
    db_session.commit()

    db_session.add_all(
        [
            Suggestion(id_user=admin.id, suggestion="Sugerencia del administrador"),
            Suggestion(id_user=user_one.id, suggestion="Sugerencia del primer usuario"),
            Suggestion(id_user=user_two.id, suggestion="Sugerencia del segundo usuario"),
        ]
    )
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "admin.suggest", "password": admin_pass},
    )
    assert login_response.status_code == 200

    page = client.get("/api/v1/suggestions/view")
    assert page.status_code == 200
    assert "Sugerencias de todos los usuarios" in page.text
    assert "Usuario" in page.text
    assert "admin.suggest" in page.text
    assert "first.user" in page.text
    assert "second.user" in page.text
    assert "Sugerencia del administrador" in page.text
    assert "Sugerencia del primer usuario" in page.text
    assert "Sugerencia del segundo usuario" in page.text
