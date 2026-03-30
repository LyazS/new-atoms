from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="", alias="OPENAI_MODEL")
    openai_timeout: int = Field(default=60, alias="OPENAI_TIMEOUT")
    agent_max_iterations: int = Field(default=6, alias="AGENT_MAX_ITERATIONS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file_path: str = Field(default="", alias="LOG_FILE_PATH")
    log_file_rotation: str = Field(default="10 MB", alias="LOG_FILE_ROTATION")
    log_file_retention: str = Field(default="7 days", alias="LOG_FILE_RETENTION")
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"], alias="CORS_ALLOW_ORIGINS")
    database_url: str = Field(default="sqlite:///./backend/app.db", alias="DATABASE_URL")
    auth_secret_key: str = Field(default="change-me-in-production", alias="AUTH_SECRET_KEY")
    access_token_expire_minutes: int = Field(default=120, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

settings = Settings()
