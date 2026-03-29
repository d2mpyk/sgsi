import warnings

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Evita un DeprecationWarning conocido de slowapi durante el import de app.main
# mientras la librería adopta inspect.iscoroutinefunction().
warnings.filterwarnings(
    "ignore",
    message=r"'asyncio\.iscoroutinefunction' is deprecated and slated for removal in Python 3\.16; use inspect\.iscoroutinefunction\(\) instead",
    category=DeprecationWarning,
    module=r"slowapi\.extension",
)

from app.main import app
from models.departments import Department
from utils.database import get_db, Base
from utils.init_db import seed_departments
from utils.limiter import limiter

# --- Configuración Global de DB para Pruebas ---
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Crea una nueva sesión de base de datos para una prueba."""
    # Crear tablas
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    # Limpieza
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Cliente de prueba con la dependencia de DB sobrescrita."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def seed_departments_catalog(db_session):
    """Asegura que el catálogo base de departamentos exista en cada prueba."""
    seed_departments(db_session)
    assert db_session.query(Department).count() == 6
    yield


@pytest.fixture(autouse=True)
def disable_rate_limiter():
    """Desactiva el rate limiter para evitar errores 429 en pruebas."""
    limiter.enabled = False
    yield
    limiter.enabled = True
