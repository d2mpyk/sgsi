from fastapi import FastAPI, Request, status
from starlette.exceptions import HTTPException as StarletteHTTPException

# Para enviar respuestas HTML
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sys
import os

# Importa la instancia del limiter API
from slowapi.errors import RateLimitExceeded
from utils.limiter import limiter
from utils.config import get_settings
from utils.auth import verify_access_token

# Imports Locales
from routers import audit, auth, dashboard, documents, lms, media, suggestions, users
from utils.database import Base, engine
from utils.init_db import (
    get_init_config,
    init_approved_users,
)
from utils.lms_period_rollover import ensure_lms_period_rollover
from utils.lms_seed import seed_lms_catalog
from utils.middleware import HTMLAuthMiddleware

# Verificación de configuraciones iniciales
get_init_config()
settings = get_settings()
# Instancia la ceación de la base y sus tablas sino existen
Base.metadata.create_all(bind=engine)
# Verificación inicial de base de datos
init_approved_users()
seed_lms_catalog()
ensure_lms_period_rollover()

# Instancia la aplicación de FastAPI
app = FastAPI(
    title="API SGSI Documentation",
    description="Esta es una app en FastAPI para Documentación de un SGSI",
    version="5.3.1",
    # Code Quality: No hardcodear root_path. Leer de variable de entorno o dejar vacío.
    # En producción (CentOS) se debe configurar Apache correctamente o pasar --root-path en uvicorn.
    root_path=os.getenv("ROOT_PATH", "/sgsi"),
)

# Middleware
app.add_middleware(HTMLAuthMiddleware)

# Montar archivos estáticos (CSS/JS/Imagenes)
app.mount("/static", StaticFiles(directory="static"), name="static")
# Monta los archivos de imagenes de usuario
app.mount("/media", StaticFiles(directory="media"), name="media")

# Configurar motor de plantillas
templates = Jinja2Templates(directory="templates")

# Añadir el limiter al estado de la aplicación
app.state.limiter = limiter
app.state.company_name = settings.COMPANY_NAME.get_secret_value()
app.state.project_name = settings.PROJECT_NAME.get_secret_value()
app.state.api_prefix = settings.API_PREFIX
app.state.dashboard_w3css_url = settings.DASHBOARD_W3CSS_URL
app.state.auth_w3css_url = settings.AUTH_W3CSS_URL
app.state.google_fonts_url = settings.GOOGLE_FONTS_URL
app.state.fontawesome_url = settings.FONTAWESOME_URL
app.state.chart_js_url = settings.CHART_JS_URL
app.state.project_repository_url = settings.PROJECT_REPOSITORY_URL
app.state.w3css_docs_url = settings.W3CSS_DOCS_URL

# Añade un manejador de excepciones para RateLimitExceeded
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": f"Límite de peticiones excedido: {exc.detail}"},
    )


def _client_wants_html(request: Request) -> bool:
    """Detecta si el cliente espera una respuesta HTML de navegador."""
    accept_header = request.headers.get("accept", "").lower()
    return request.method == "GET" and "text/html" in accept_header


def _get_error_redirect_context(request: Request) -> tuple[str, str]:
    """
    Retorna URL y texto del botón para redirección:
    - Dashboard si token es válido.
    - Login si no hay token o no es válido.
    """
    redirect_url = str(request.url_for("login"))
    button_text = "Ir a Inicio de Sesión"

    token = request.cookies.get("access_token")
    if token:
        try:
            verify_access_token(token)
            redirect_url = str(request.url_for("dashboard"))
            button_text = "Ir al Dashboard"
        except Exception:
            pass

    return redirect_url, button_text


def _render_error_page(
    request: Request,
    template_name: str,
    status_code: int,
    title: str,
    heading: str,
    description: str,
):
    redirect_url, button_text = _get_error_redirect_context(request)
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context={
            "title": title,
            "error_heading": heading,
            "error_description": description,
            "redirect_url": redirect_url,
            "button_text": button_text,
        },
        status_code=status_code,
    )


@app.exception_handler(status.HTTP_404_NOT_FOUND)
async def not_found_handler(request: Request, exc):
    wants_html = _client_wants_html(request)

    if not wants_html:
        detail = getattr(exc, "detail", "Not Found")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": detail if detail else "Not Found"},
        )

    return _render_error_page(
        request=request,
        template_name="errors/404.html",
        status_code=status.HTTP_404_NOT_FOUND,
        title="Página no encontrada",
        heading="Error 404",
        description="El contenido que intentas abrir no existe o fue movido dentro del portal SGSI.",
    )


@app.exception_handler(status.HTTP_403_FORBIDDEN)
async def forbidden_handler(request: Request, exc: StarletteHTTPException):
    if not _client_wants_html(request):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.detail if exc.detail else "Forbidden"},
        )

    return _render_error_page(
        request=request,
        template_name="errors/403.html",
        status_code=status.HTTP_403_FORBIDDEN,
        title="Acceso denegado",
        heading="Error 403",
        description="No tienes permisos suficientes para acceder a este recurso del portal SGSI.",
    )


@app.exception_handler(Exception)
async def internal_server_error_handler(request: Request, exc: Exception):
    if not _client_wants_html(request):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal Server Error"},
        )

    return _render_error_page(
        request=request,
        template_name="errors/500.html",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Error interno del servidor",
        heading="Error 500",
        description="Ocurrió un fallo inesperado en el servidor. Puedes volver al flujo principal desde el botón.",
    )

# Enrutadores
api_prefix = settings.API_PREFIX.rstrip("/")
app.include_router(auth.router, prefix=f"{api_prefix}/auth", tags=["Auth"])
app.include_router(dashboard.router, prefix=f"{api_prefix}/dashboard", tags=["Dashboard"])
app.include_router(documents.router, prefix=f"{api_prefix}/documents", tags=["Documents"])
app.include_router(lms.router, prefix=f"{api_prefix}", tags=["LMS"])
app.include_router(audit.router, prefix=f"{api_prefix}/audit", tags=["Audit"])
app.include_router(suggestions.router, prefix=f"{api_prefix}/suggestions", tags=["Suggestions"])
app.include_router(users.router, prefix=f"{api_prefix}/users", tags=["Users"])
app.include_router(media.router, prefix=f"{api_prefix}/media", tags=["Media"])

# Muestra la pagina principal del sitio
@app.get(
    "/",
    response_class=RedirectResponse,
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    include_in_schema=False,
)
def inicio(request: Request):
    """Redirige a la página de login principal."""
    return RedirectResponse(url=request.url_for("login"))


@app.api_route(
    "/favicon.ico",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def favicon():
    """Entrega el favicon del sitio."""
    return FileResponse(
        path=os.path.join("static", "favicon.ico"),
        media_type="image/x-icon",
    )


# -----------------------------------------------
# Muestra la pagina de recuperar contraseña
@app.get(
    "/forgot-password",
    name="forgot-password",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def forgot_password_view(request: Request):
    """Renderiza la página recuperar contraseña"""
    return templates.TemplateResponse(
        request=request,
        name="auth/forgot-password.html",
        context={"title": "Recupera tu contraseña"},
    )


# -----------------------------------------------
# Muestra la pagina de resetear contraseña
@app.get(
    "/reset-password",
    name="reset-password",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def reset_password_view(request: Request):
    """Renderiza la página de resetear contraseña"""
    return templates.TemplateResponse(
        request=request,
        name="auth/reset-password.html",
        context={"title": "Restablecer contraseña"},
    )
