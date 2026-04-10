from fastapi import FastAPI, Request, status

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

# Imports Locales
from routers import audit, auth, dashboard, documents, media, suggestions, users
from utils.database import Base, engine
from utils.init_db import (
    get_init_config,
    init_iso_controls,
    init_approved_users,
)
from utils.middleware import HTMLAuthMiddleware

# Verificación de configuraciones iniciales
get_init_config()
settings = get_settings()
# Instancia la ceación de la base y sus tablas sino existen
Base.metadata.create_all(bind=engine)
# Verificación inicial de base de datos
init_approved_users()
init_iso_controls()

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

# Enrutadores
api_prefix = settings.API_PREFIX.rstrip("/")
app.include_router(auth.router, prefix=f"{api_prefix}/auth", tags=["Auth"])
app.include_router(dashboard.router, prefix=f"{api_prefix}/dashboard", tags=["Dashboard"])
app.include_router(documents.router, prefix=f"{api_prefix}/documents", tags=["Documents"])
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
