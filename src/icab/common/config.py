from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ICABSettings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        validation_alias="ICAB_DATABASE_URL",
        min_length=1,
    )

    neo4j_uri: str = Field(
        validation_alias="ICAB_NEO4J_URI",
        min_length=1,
    )

    neo4j_username: str = Field(
        validation_alias="ICAB_NEO4J_USERNAME",
        min_length=1,
    )

    neo4j_password: str = Field(
        validation_alias="ICAB_NEO4J_PASSWORD",
        min_length=1,
    )


def get_settings() -> ICABSettings:
    """Return the current ICAB application settings."""
    return ICABSettings()
