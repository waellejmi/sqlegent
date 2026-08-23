from sqlalchemy import create_engine, text

from config.env_config import EnvConfig

config = EnvConfig()


def test_database_connection():
    engine = create_engine(config.AZURE_DB_CONNTECTION)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
