from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="./.env", env_file_encoding="utf-8")

    db_url: str = Field(alias="DATABASE_URL")

    github_client_id: str = Field(alias="GITHUB_CLIENT_ID")
    github_client_secret: str = Field(alias="GITHUB_CLIENT_SECRET")
    github_redirect_uri: str = Field(alias="GITHUB_REDIRECT_URI")

    frontend_url: str = Field(alias="FRONTEND_URL")
    frontend_redirect_uri: str = Field(alias="FRONTEND_REDIRECT_URI")

    access_token_expire_minutes: int = Field(alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_minutes: int = Field(alias="REFRESH_TOKEN_EXPIRE_MINUTES")

    jwt_secret_key: str = Field(alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(alias="JWT_ALGORITHM")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore
