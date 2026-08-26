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

    # Resend (optional  if unset, reset links are logged to console instead of emailed)
    resend_api_key: str = ""
    email_from: str = "SmartStock AI <onboarding@resend.dev>"

    # Comma-separated list of allowed browser origins for CORS, e.g.
    # "https://ai-inventorysystem.vercel.app,https://smartstock.co.ke".
    # Left empty, only frontend_base_url is allowed. Never use "*" in
    # production  this app relies on cookies, which requires an explicit
    # origin allow-list rather than a wildcard.
    cors_origins: str = ""

    class Config:
        env_file = ".env"

    @property
    def allowed_origins(self) -> list[str]:
        origins = {self.frontend_base_url.rstrip("/")}
        for origin in self.cors_origins.split(","):
            origin = origin.strip().rstrip("/")
            if origin:
                origins.add(origin)
        return list(origins)


@lru_cache()
def get_settings():
    return Settings()
