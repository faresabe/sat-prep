from pydantic_settings import BaseSettings, SettingsConfigDict


def _fix_db_url(url: str) -> str:
    """
    Render (and some other hosts) provide a standard postgres:// URL.
    SQLAlchemy asyncpg requires postgresql+asyncpg://.
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
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
    cors_origins: list[str] = [""]

    def model_post_init(self, __context: object) -> None:
        # Fix postgres:// → postgresql+asyncpg:// for Render compatibility
        object.__setattr__(self, "database_url", _fix_db_url(self.database_url))
        object.__setattr__(self, "database_url_migration", _fix_db_url(self.database_url_migration))
        object.__setattr__(self, "database_url_grader", _fix_db_url(self.database_url_grader))


settings = Settings()
