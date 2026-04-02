from sqlalchemy import create_engine, text

engine = create_engine("mssql+pymssql://sa:ChinookPass123%21@localhost:1433/Chinook")

with engine.connect() as conn:
    result = conn.execute(
        text(
            "SELECT table_name FROM INFORMATION_SCHEMA.TABLES WHERE table_type = 'BASE TABLE' ORDER BY table_name"
        )
    )
    for row in result:
        print(row[0])
