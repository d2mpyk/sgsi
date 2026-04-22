from pathlib import Path
import json
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, inspect, text
from sqlalchemy.orm import Session
import sys

from models.departments import Department
from models.lms import LMSPost
from models.users import ApprovedUsers, User
from services import lms_service
from utils.auth import hash_password
from utils.config import get_settings

from .database import Base, SessionLocal, engine

# Obtener las variables de entorno
settings = get_settings()

DEFAULT_DEPARTMENTS = [
    "Call Center",
    "Desarrollo",
    "Dirección Ejecutiva",
    "Infraestructura",
    "Operaciones",
    "Recursos Humanos",
]

LMS_REQUIRED_TABLES = [
    "lms_posts",
    "lms_quizzes",
    "lms_quiz_questions",
    "lms_quiz_options",
    "lms_themes",
]

LMS_QUIZ_TABLES = [
    "lms_quizzes",
    "lms_quiz_questions",
    "lms_quiz_options",
]

LMS_BOOTSTRAP_DATA_PATH = (
    Path(__file__).resolve().parents[1] / "utils" / "bootstrap" / "lms_bootstrap_data.json"
)


def _sanitize_for_mysql_utf8(value: str | None) -> str:
    """
    Elimina caracteres fuera del BMP (4 bytes UTF-8) para compatibilidad
    con despliegues MySQL/MariaDB en utf8 (3 bytes).
    """
    if not value:
        return ""
    return "".join(ch for ch in value if ord(ch) <= 0xFFFF)

def get_init_config():
    """Verifica si el archivo config esta ok"""
    # Verificación de seguridad
    SECRET_KEY = settings.SECRET_KEY.get_secret_value()
    SECRET_KEY_CHECK_MAIL = settings.SECRET_KEY_CHECK_MAIL.get_secret_value()
    SECURITY_PASSWD_SALT = settings.SECURITY_PASSWD_SALT.get_secret_value()
    if (
        SECRET_KEY is None
        or not SECRET_KEY.strip()
        or SECRET_KEY_CHECK_MAIL is None
        or not SECRET_KEY_CHECK_MAIL.strip()
        or SECURITY_PASSWD_SALT is None
        or not SECURITY_PASSWD_SALT.strip()
    ):
        print("=" * 60)
        print("❌ FATAL ERROR: Configuración de seguridad inválida.", file=sys.stderr)
        print(
            "   La variables de AAA y de verificación de correo no están definidas.",
            file=sys.stderr,
        )
        print("=" * 60)
        # Detiene la ejecución del script retornando un código de error (1)
        sys.exit(1)

    # Verificación de los datos del usuario Principal
    ADMIN = settings.ADMIN.get_secret_value()
    NAME = settings.NAME.get_secret_value()
    if ADMIN is None or not ADMIN.strip() or NAME is None or not NAME.strip():
        print("=" * 60)
        print("❌ FATAL ERROR: Configuración de aplicación inválida.", file=sys.stderr)
        print(
            "   La variable de entorno 'ADMIN' o 'NAME' no está definida.",
            file=sys.stderr,
        )
        print("=" * 60)
        # Detiene la ejecución del script retornando un código de error (1)
        sys.exit(1)

    # Verificación de los datos del correo
    EMAIL_SERVER = settings.EMAIL_SERVER.get_secret_value()
    EMAIL_PORT = settings.EMAIL_PORT.get_secret_value()
    EMAIL_USER = settings.EMAIL_USER.get_secret_value()
    EMAIL_PASSWD = settings.EMAIL_PASSWD.get_secret_value()
    if (
        EMAIL_SERVER is None
        or not EMAIL_SERVER.strip()
        or EMAIL_PORT is None
        or not EMAIL_PORT.strip()
        or EMAIL_USER is None
        or not EMAIL_USER.strip()
        or EMAIL_PASSWD is None
        or not EMAIL_PASSWD.strip()
    ):
        print("=" * 60)
        print("❌ FATAL ERROR: Configuración de aplicación inválida.", file=sys.stderr)
        print(
            "   Las variables de entorno de correo no están definida.", file=sys.stderr
        )
        print("=" * 60)
        # Detiene la ejecución del script retornando un código de error (1)
        sys.exit(1)


def init_approved_users():
    db = SessionLocal()
    try:
        default_department_id = seed_departments(db)
        user = db.query(ApprovedUsers).first()

        # Si no hay usuarios
        if not user:
            # Primero lo agregamos a ApprovedUsers
            ADMIN = settings.ADMIN.get_secret_value()
            user = ApprovedUsers(email=ADMIN)
            db.add(user)
            db.commit()
            db.refresh(user)
            # Luego lo agregamos a Users
            NAME = settings.NAME.get_secret_value()
            user_admin = User(
                username=NAME,
                email=ADMIN,
                password_hash=hash_password("admin"),
                role="admin",
                is_active=True,
                image_file="dxtrthink.png",
                department_id=default_department_id,
            )
            db.add(user_admin)
            db.commit()
            db.refresh(user_admin)

    except Exception as e:
        print(f"Error: Inicializando DB: {e}, ", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


def seed_departments(db: Session) -> int:
    """Crea el catálogo base de departamentos si aún no existe."""
    existing = {
        department.departamento: department
        for department in db.query(Department).all()
    }

    created = False
    for department_name in DEFAULT_DEPARTMENTS:
        if department_name not in existing:
            db.add(Department(departamento=department_name))
            created = True

    if created:
        db.commit()

    ordered_departments = (
        db.query(Department)
        .order_by(Department.id.asc())
        .all()
    )

    if not ordered_departments:
        raise RuntimeError("No fue posible inicializar el catálogo de departamentos.")

    return ordered_departments[0].id


def ensure_lms_bootstrap_data():
    """
    Garantiza que el módulo LMS cuente con tablas y datos base en arranque:
    - Verifica/crea `lms_themes`.
    - Verifica existencia de tablas LMS requeridas.
    - Si falta población en posts/quiz/themes, repuebla desde snapshot local.
    """
    db = SessionLocal()
    try:
        _ensure_lms_themes_table(db)
        _ensure_lms_required_tables_exist(db)

        table_counts = _get_lms_table_counts(db)
        missing_required = [name for name, qty in table_counts.items() if qty == 0]
        if not missing_required:
            return

        seed_payload = _load_lms_bootstrap_payload()
        if table_counts["lms_posts"] == 0:
            _seed_lms_posts(db, seed_payload)
            table_counts["lms_posts"] = _count_rows(db, "lms_posts")

        if table_counts["lms_themes"] == 0:
            _seed_lms_themes(db, seed_payload)
            table_counts["lms_themes"] = _count_rows(db, "lms_themes")

        if any(table_counts[name] == 0 for name in LMS_QUIZ_TABLES):
            _seed_lms_quizzes(db, seed_payload)
    except Exception as e:
        print(f"Error: Inicializando bootstrap LMS: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


def _ensure_lms_required_tables_exist(db: Session) -> None:
    inspector = inspect(db.bind)
    existing = set(inspector.get_table_names())
    missing = [table_name for table_name in LMS_REQUIRED_TABLES if table_name not in existing]
    if missing:
        Base.metadata.create_all(bind=engine)
        inspector = inspect(db.bind)
        existing = set(inspector.get_table_names())
        missing = [table_name for table_name in LMS_REQUIRED_TABLES if table_name not in existing]
        if missing:
            raise RuntimeError(
                f"Tablas LMS requeridas no disponibles tras create_all: {', '.join(missing)}"
            )


def _ensure_lms_themes_table(db: Session) -> None:
    """
    Crea `lms_themes` de forma portable si no existe.
    Se maneja por SQLAlchemy Core para ser compatible con MariaDB/MySQL y SQLite.
    """
    metadata = MetaData()
    themes_table = Table(
        "lms_themes",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("name", String(180), nullable=False),
        Column("slug", String(180), nullable=False, unique=True, index=True),
        Column("display_order", Integer, nullable=False, default=1),
        Column("is_active", Boolean, nullable=False, default=True),
        Column("created_at", DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
    )
    metadata.create_all(bind=db.bind, tables=[themes_table], checkfirst=True)


def _get_lms_table_counts(db: Session) -> dict[str, int]:
    return {table_name: _count_rows(db, table_name) for table_name in LMS_REQUIRED_TABLES}


def _count_rows(db: Session, table_name: str) -> int:
    # `table_name` viene de una lista cerrada definida en código.
    return int(db.execute(text(f"SELECT COUNT(1) FROM {table_name}")).scalar() or 0)


def _load_lms_bootstrap_payload() -> dict:
    if not LMS_BOOTSTRAP_DATA_PATH.exists():
        raise RuntimeError(
            "No existe snapshot LMS para bootstrap en "
            f"{LMS_BOOTSTRAP_DATA_PATH}"
        )
    return json.loads(LMS_BOOTSTRAP_DATA_PATH.read_text(encoding="utf-8"))


def _seed_lms_posts(db: Session, payload: dict) -> None:
    for item in payload.get("posts", []):
        html_content = _sanitize_for_mysql_utf8(item.get("html_content", ""))
        title = _sanitize_for_mysql_utf8(item["title"])
        category = _sanitize_for_mysql_utf8(item.get("category", "Capacitación SGSI"))
        post = LMSPost(
            title=title,
            slug=item["slug"],
            category=category,
            version=item.get("version", "1.0"),
            status=item.get("status", "published"),
            html_content=html_content,
            porcentaje_aprobacion=float(item.get("porcentaje_aprobacion", 80.0)),
            max_intentos=int(item.get("max_intentos", 3)),
            created_by_id=item.get("created_by_id"),
        )
        db.add(post)
    db.commit()


def _seed_lms_themes(db: Session, payload: dict) -> None:
    theme_rows = payload.get("themes", [])
    if not theme_rows:
        posts = db.query(LMSPost).order_by(LMSPost.id.asc()).all()
        theme_rows = [
            {
                "name": post.title,
                "slug": post.slug,
                "display_order": idx,
                "is_active": True,
            }
            for idx, post in enumerate(posts, start=1)
        ]

    for row in theme_rows:
        db.execute(
            text(
                """
                INSERT INTO lms_themes (name, slug, display_order, is_active, created_at, updated_at)
                VALUES (:name, :slug, :display_order, :is_active, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                "name": row["name"],
                "slug": row["slug"],
                "display_order": int(row.get("display_order", 1)),
                "is_active": bool(row.get("is_active", True)),
            },
        )
    db.commit()


def _seed_lms_quizzes(db: Session, payload: dict) -> None:
    posts_by_slug = {post.slug: post for post in db.query(LMSPost).all()}
    quizzes = payload.get("quizzes", [])
    if not quizzes:
        return

    for quiz_item in quizzes:
        post_slug = quiz_item.get("post_slug")
        post = posts_by_slug.get(post_slug)
        if post is None:
            continue
        lms_service.upsert_quiz(
            db=db,
            post_id=post.id,
            title=quiz_item.get("title", f"Evaluación - {post.title}"),
            instructions=quiz_item.get("instructions", ""),
            version=quiz_item.get("version", "1.0"),
            is_active=bool(quiz_item.get("is_active", True)),
            questions=quiz_item.get("questions", []),
        )
