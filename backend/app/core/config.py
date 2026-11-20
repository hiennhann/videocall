from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, StringConstraints, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
DEMO_ADMIN_EMAIL = "admin@videocall.example.com"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(hide_input_in_errors=True)

    env: Literal["dev", "test", "prod"]
    database_url: SecretStr
    jwt_secret: SecretStr
    turn_secret: SecretStr = Field(min_length=1)
    turn_urls: NonEmptyString
    allowed_origins: NonEmptyString
    public_base_url: str = ""
    forwarded_allow_ips: str = ""
    admin_allowed_ips: str = ""
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    prometheus_url: str = ""
    sfu_url: str = ""
    avatar_storage_dir: Path = Path(__file__).resolve().parents[3] / ".data" / "avatars"

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except (ArgumentError, ValueError):
            raise ValueError("DATABASE_URL phải là URL PostgreSQL hợp lệ.") from None
        if url.drivername != "postgresql+asyncpg" or not url.database:
            raise ValueError("DATABASE_URL phải dùng postgresql+asyncpg và có tên database.")
        return value

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode()) < 32:
            raise ValueError("JWT_SECRET phải có ít nhất 32 byte.")
        return value

    @model_validator(mode="after")
    def validate_production_settings(self) -> Self:
        if self.env == "prod" and not all(
            value.strip()
            for value in (self.public_base_url, self.forwarded_allow_ips, self.admin_allowed_ips)
        ):
            raise ValueError("Prod cần PUBLIC_BASE_URL, FORWARDED_ALLOW_IPS và ADMIN_ALLOWED_IPS.")
        return self
