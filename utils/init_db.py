from sqlalchemy.orm import Session
import sys
import os
import re

from models.departments import Department
from models.iso_controls import ISOControl
from models.users import ApprovedUsers, User
from utils.auth import hash_password
from utils.config import get_settings

from .database import SessionLocal

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

ISO_THEME_BY_DOMAIN = {
    "5": "Organizacionales",
    "6": "Personas",
    "7": "Físicos",
    "8": "Tecnológicos",
}


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


def _resolve_iso_controls_source_path(controls_file: str | None = None) -> str:
    if controls_file:
        return controls_file
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "SGSI-All_Controls-93.txt")


def parse_iso_controls_file(controls_file: str | None = None) -> list[dict[str, str]]:
    """
    Parsea el archivo SGSI-All_Controls-93.txt y retorna controles normalizados.

    Estructura esperada por item:
    - tema: Organizacionales | Personas | Físicos | Tecnológicos
    - control: A.5.1, A.6.8, ...
    - nombre: Nombre del control
    """
    source_path = _resolve_iso_controls_source_path(controls_file)
    with open(source_path, "r", encoding="utf-8") as source:
        content = source.read().splitlines()

    control_line_regex = re.compile(r'^"(?P<control>A\.(?P<domain>[5-8])\.\d+)\s+(?P<name>.+)"[,]?$')
    controls: list[dict[str, str]] = []
    seen_controls: set[str] = set()

    for raw_line in content:
        line = raw_line.strip()
        match = control_line_regex.match(line)
        if not match:
            continue

        control_code = match.group("control").strip()
        domain = match.group("domain")
        control_name = match.group("name").strip()
        theme = ISO_THEME_BY_DOMAIN.get(domain)

        if theme is None:
            continue
        if control_code in seen_controls:
            continue

        controls.append(
            {
                "tema": theme,
                "control": control_code,
                "nombre": control_name,
            }
        )
        seen_controls.add(control_code)

    return sorted(
        controls,
        key=lambda item: tuple(int(part) if part.isdigit() else part for part in item["control"].replace("A.", "").split(".")),
    )


def seed_iso_controls(db: Session, controls_file: str | None = None) -> int:
    """Carga el catálogo ISO 27001 en la tabla iso_controls de forma idempotente."""
    parsed_controls = parse_iso_controls_file(controls_file=controls_file)
    if not parsed_controls:
        raise RuntimeError("No se encontraron controles ISO válidos para poblar iso_controls.")

    existing_by_control = {
        row.control: row
        for row in db.query(ISOControl).all()
    }

    created = 0
    updated = 0
    for item in parsed_controls:
        existing = existing_by_control.get(item["control"])
        if existing is None:
            db.add(
                ISOControl(
                    tema=item["tema"],
                    control=item["control"],
                    nombre=item["nombre"],
                )
            )
            created += 1
            continue

        if existing.tema != item["tema"] or existing.nombre != item["nombre"]:
            existing.tema = item["tema"]
            existing.nombre = item["nombre"]
            updated += 1

    if created or updated:
        db.commit()

    return len(parsed_controls)


def init_iso_controls():
    """Inicializa el catálogo de controles ISO en el arranque de la app."""
    db = SessionLocal()
    try:
        seed_iso_controls(db)
    except Exception as e:
        print(f"Error: Inicializando catálogo ISO controls: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()
