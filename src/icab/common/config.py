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

    mqtt_host: str = Field(
        default="localhost",
        validation_alias="ICAB_MQTT_HOST",
        min_length=1,
    )

    mqtt_port: int = Field(
        default=1883,
        validation_alias="ICAB_MQTT_PORT",
        gt=0,
    )

    llm_provider: str | None = Field(
        default=None,
        validation_alias="ICAB_LLM_PROVIDER",
    )

    llm_base_url: str | None = Field(
        default=None,
        validation_alias="ICAB_LLM_BASE_URL",
    )

    llm_api_key: str | None = Field(
        default=None,
        validation_alias="ICAB_LLM_API_KEY",
    )

    llm_model: str | None = Field(
        default=None,
        validation_alias="ICAB_LLM_MODEL",
    )

    i3x_base_url: str = Field(
        default="http://localhost:8090",
        validation_alias="ICAB_I3X_BASE_URL",
        min_length=1,
        description=(
            "ICAB's own private, TEP-backed i3X instance (see "
            "services/i3x/ and docs/architecture/i3x-private-server.md) "
            "-- NOT the public https://api.i3x.dev/v1 conformance server, "
            "which is read-only reference infrastructure ICAB does not "
            "write to."
        ),
    )


def get_settings() -> ICABSettings:
    """Return the current ICAB application settings."""
    return ICABSettings()
