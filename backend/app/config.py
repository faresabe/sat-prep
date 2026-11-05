import re
from pydantic_settings import BaseSettings, SettingsConfigDict


def _fix_db_url(url: str) -> str:
    """
    Normalize any PostgreSQL connection URL to the form SQLAlchemy asyncpg
    requires: postgresql+asyncpg://...

    Handles:
      postgres://...            → postgresql+asyncpg://...
      postgresql://...          → postgresql+asyncpg://...
      postgresql+asyncpg://...  → unchanged

    Also strips query parameters that asyncpg does not support
    (e.g. sslmode=require from Render external URLs). asyncpg handles
    SSL automatically on Render's internal network; if SSL is explicitly
    needed it must be passed as connect_args, not in the URL.
    """
    # Normalise scheme
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # postgresql+asyncpg:// already — leave unchanged

    # Strip unsupported query params (sslmode, etc.)
    # asyncpg uses its own ssl= connect_arg; query-string ssl params cause errors
    url = re.sub(r'\?.*$', '', url)

    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "satprep"
    environment: str = "development"
    debug: bool = True

    database_url: str
    database_url_migration: str
    database_url_grader: str

    redis_url: str = ""
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # Comma-separated or JSON list of allowed CORS origins.
    # Default allows local dev. On Render set CORS_ORIGINS to your Vercel URL.
    # Example: '["https://sat-prep.vercel.app","http://localhost:5173"]'
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    def model_post_init(self, __context: object) -> None:
        object.__setattr__(self, "database_url", _fix_db_url(self.database_url))
        object.__setattr__(self, "database_url_migration", _fix_db_url(self.database_url_migration))
        object.__setattr__(self, "database_url_grader", _fix_db_url(self.database_url_grader))


settings = Settings()
