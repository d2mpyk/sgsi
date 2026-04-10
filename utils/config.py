from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    ADMIN: SecretStr
    NAME: SecretStr
    COMPANY_NAME: SecretStr
    PROJECT_NAME: SecretStr
    DB_USER: SecretStr
    DB_PASSWORD: SecretStr
    DB_HOST: SecretStr
    DB_PORT: int = 3306
    DB_NAME: SecretStr
    SECRET_KEY: SecretStr
    ALGORITHM: SecretStr
    ACCESS_TOKEN_EXPIRE_MINUTES: SecretStr
    SECRET_KEY_CHECK_MAIL: SecretStr
    SECURITY_PASSWD_SALT: SecretStr
    DOMINIO: SecretStr
    EMAIL_SERVER: SecretStr
    EMAIL_PORT: SecretStr
    EMAIL_USER: SecretStr
    EMAIL_PASSWD: SecretStr
    UTC_SERVER: str = "America/Santiago"
    API_PREFIX: str = "/api/v1"
    DASHBOARD_W3CSS_URL: str = "https://www.w3schools.com/w3css/4/w3.css"
    AUTH_W3CSS_URL: str = "https://www.w3schools.com/w3css/5/w3.css"
    GOOGLE_FONTS_URL: str = "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Montserrat:wght@600;700;800&display=swap"
    FONTAWESOME_URL: str = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css"
    CHART_JS_URL: str = "https://cdn.jsdelivr.net/npm/chart.js"
    PROJECT_REPOSITORY_URL: str = "https://github.com/d2mpyk/sgsi"
    W3CSS_DOCS_URL: str = "https://www.w3schools.com/w3css/default.asp"
    LOG_MAX_BYTES: int = 5242880  # 5 MB por defecto
    LOG_BACKUP_COUNT: int = 5


# Para cargar las variables de entorno
def get_settings():
    return Settings()
