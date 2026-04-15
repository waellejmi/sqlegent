from sqlalchemy import create_engine, text

engine_url = "sqlite:////home/wael/Code/sql-agent/.app_cache/context_layer.sqlite"

engine = create_engine(engine_url)

with engine.connect() as conn:
    result = conn.execute(
        text(
            "SELECT * FROM 'context_chunks' WHERE id = '9e1da605-4713-4bc2-8dca-266699b36e43';"
        )
    )
    for row in result:
        print(row)
