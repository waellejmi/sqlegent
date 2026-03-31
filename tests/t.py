from sqlalchemy import create_engine, text

engine_url = "oracle+oracledb://chinook_user:ChinookPass123%21@localhost:1521/?service_name=FREEPDB1"

engine = create_engine(engine_url)

with engine.connect() as conn:
    result = conn.execute(
        text("SELECT table_name FROM user_tables ORDER BY table_name")
    )
    for row in result:
        print(row[0])
