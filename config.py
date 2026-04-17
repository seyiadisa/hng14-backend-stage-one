from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    db_url: str = Field(alias="DATABASE_URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore
