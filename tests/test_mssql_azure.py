from sqlalchemy import create_engine, text

from config.env_config import EnvConfig

config = EnvConfig()


engine = create_engine(config.AZURE_DB_CONNTECTION)
with engine.connect() as conn:
    result = conn.execute(
        text(
            "SELECT table_name FROM INFORMATION_SCHEMA.TABLES WHERE table_type = 'BASE TABLE' ORDER BY table_name"
        )
    )
    for row in result:
        print(row[0])
