"""Settings come from environment variables (prefix WEAZEL_) or core-api/.env. No secret has a usable default."""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRET = "change-me-to-a-long-random-string"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WEAZEL_", env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"  # development | test | production
    DATABASE_URL: str = "postgresql+psycopg2://weazel:weazel_dev@127.0.0.1:5432/weazel"

    # local    : no login. Every request is the single local admin. Development on your own PC only.
    # password : email + password accounts created by an administrator.
    # fivem    : reserved for the FiveM session bridge (Phase 5). The API refuses to start with it until it exists.
    AUTH_MODE: str = "password"
    JWT_SECRET: str = PLACEHOLDER_SECRET
    ACCESS_TOKEN_MINUTES: int = 30
    LOCAL_ADMIN_NAME: str = "Local Administrator"

    CORS_ORIGINS: str = "http://localhost:3000"
    PUBLIC_READ_ENABLED: bool = True  # /public/articles (published articles only, no auth)
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_WINDOW_SECONDS: int = 300

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _guards(self):
        if self.AUTH_MODE not in {"local", "password", "fivem"}:
            raise ValueError("WEAZEL_AUTH_MODE must be local, password or fivem")
        if self.AUTH_MODE == "fivem":
            raise ValueError("WEAZEL_AUTH_MODE=fivem is not implemented yet (FiveM bridge is Phase 5)")
        if self.AUTH_MODE == "local" and self.ENVIRONMENT == "production":
            raise ValueError("WEAZEL_AUTH_MODE=local is not allowed when WEAZEL_ENVIRONMENT=production")
        if self.AUTH_MODE == "password" and self.ENVIRONMENT != "test":
            if self.JWT_SECRET == PLACEHOLDER_SECRET or len(self.JWT_SECRET) < 32:
                raise ValueError("Set WEAZEL_JWT_SECRET to a random string of at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
