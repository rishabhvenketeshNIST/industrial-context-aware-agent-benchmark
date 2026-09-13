from icab.common.config import ICABSettings


def test_settings_load_from_env_file():
    settings = ICABSettings(
        _env_file=".env",
    )

    assert settings.database_url == ("postgresql://icab:icab@localhost:5432/icab")

    assert settings.neo4j_uri == "bolt://localhost:7687"
    assert settings.neo4j_username == "neo4j"
    assert settings.neo4j_password == "icabpassword"
