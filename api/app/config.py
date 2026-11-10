from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from environment variables (or a .env file in development)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://kasuwa:kasuwa@localhost:5432/kasuwa"
    admin_token: str = "change-me"                 # protects POST /engine/run
    cors_origins: str = "*"                        # comma-separated, e.g. https://kasuwa.com.ng
    timezone: str = "Africa/Lagos"


settings = Settings()
