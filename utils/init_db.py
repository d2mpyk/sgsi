from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
import sys

from models.departments import Department
from models.users import ApprovedUsers, User
from utils.auth import hash_password
from utils.config import get_settings

from .database import SessionLocal, engine

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


def ensure_document_reads_download_at_column():
    """Agrega la columna download_at a document_reads si aún no existe."""
    inspector = inspect(engine)

    try:
        if "document_reads" not in inspector.get_table_names():
            return

        existing_columns = {
            column["name"] for column in inspector.get_columns("document_reads")
        }

        if "download_at" not in existing_columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE document_reads ADD COLUMN download_at DATETIME")
                )
    except Exception as e:
        print(
            f"Error: No se pudo verificar/agregar la columna download_at: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


def ensure_suggestions_table():
    """Crea la tabla suggestions si aún no existe en bases existentes."""
    inspector = inspect(engine)

    try:
        if "suggestions" in inspector.get_table_names():
            return

        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE suggestions (
                        id INTEGER NOT NULL AUTO_INCREMENT,
                        id_user INTEGER NOT NULL,
                        suggestion TEXT NOT NULL,
                        created_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        INDEX ix_suggestions_id (id),
                        INDEX ix_suggestions_id_user (id_user),
                        CONSTRAINT fk_suggestions_users
                            FOREIGN KEY (id_user) REFERENCES users (id)
                    )
                    """
                )
            )
    except Exception as e:
        print(
            f"Error: No se pudo verificar/crear la tabla suggestions: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


def ensure_users_department_column():
    """Agrega la columna department_id a users si aún no existe y la inicializa."""
    inspector = inspect(engine)

    try:
        if "users" not in inspector.get_table_names():
            return

        existing_columns = {column["name"] for column in inspector.get_columns("users")}
        default_department_id = None

        with SessionLocal() as db:
            default_department_id = seed_departments(db)

        if "department_id" not in existing_columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN department_id INTEGER")
                )

        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE users SET department_id = :department_id "
                    "WHERE department_id IS NULL"
                ),
                {"department_id": default_department_id},
            )
    except Exception as e:
        print(
            f"Error: No se pudo verificar/agregar la columna department_id: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

