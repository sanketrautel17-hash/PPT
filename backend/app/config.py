from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "PPT Generator"
    app_env: str = Field(default="dev", validation_alias=AliasChoices("APP_ENV", "app_env"))
    app_host: str = Field(default="0.0.0.0", validation_alias=AliasChoices("APP_HOST", "app_host"))
    app_port: int = Field(default=8000, validation_alias=AliasChoices("APP_PORT", "app_port"))
    log_level: str = Field(default="INFO", validation_alias=AliasChoices("LOG_LEVEL", "log_level"))

    # MongoDB
    mongodb_uri: str = Field(
        ...,
        validation_alias=AliasChoices("MONGODB_URI", "MONGO_DB_URL", "mongo_db_url"),
    )
    mongodb_db_name: str = Field(
        default="ppt_generator",
        validation_alias=AliasChoices("MONGODB_DB_NAME", "mongodb_db_name"),
    )
    template_bucket_name: str = Field(
        default="template_files",
        validation_alias=AliasChoices("TEMPLATE_BUCKET_NAME", "template_bucket_name"),
    )
    generated_bucket_name: str = Field(
        default="generated_files",
        validation_alias=AliasChoices("GENERATED_BUCKET_NAME", "generated_bucket_name"),
    )

    # Groq LLM (kept for backwards compat; ignored when openrouter_api_key is set)
    groq_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GROQ_API_KEY", "GROK_API_KEY", "groq_api_key", "grok_api_key"),
    )

    # OpenRouter LLM
    openrouter_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "openrouter_api_key"),
    )

    # Model names (configurable — no code changes needed to swap)
    planner_model: str = Field(
        default="google/gemini-2.0-flash-001",
        validation_alias=AliasChoices("PLANNER_MODEL", "planner_model"),
    )
    guidance_model: str = Field(
        default="google/gemini-2.0-flash-001",
        validation_alias=AliasChoices("GUIDANCE_MODEL", "guidance_model"),
    )

    # Limits
    max_template_size_mb: int = Field(
        default=50,
        validation_alias=AliasChoices("MAX_TEMPLATE_SIZE_MB", "max_template_size_mb"),
    )
    max_prompt_chars: int = Field(
        default=8000,
        validation_alias=AliasChoices("MAX_PROMPT_CHARS", "max_prompt_chars"),
    )
    max_retries: int = Field(
        default=2,
        validation_alias=AliasChoices("MAX_RETRIES", "max_retries"),
    )
    slide_generation_concurrency: int = Field(
        default=4,
        validation_alias=AliasChoices("SLIDE_GENERATION_CONCURRENCY", "slide_generation_concurrency"),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
