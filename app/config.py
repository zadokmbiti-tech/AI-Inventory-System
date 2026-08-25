from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "SmartStock AI"
    debug: bool = False
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Password reset
    reset_token_expire_minutes: int = 30
    frontend_base_url: str = "http://localhost:8000"

    # SMTP (optional — if unset, reset links are logged to console instead of emailed)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()
