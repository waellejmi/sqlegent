from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
import os

def validate_uri(uri: str) -> bool:
    try:
        url = make_url(uri)
        if url.drivername.startswith("sqlite"):
            db_path = url.database
            if db_path and db_path != ":memory:":
                if not os.path.exists(db_path):
                    print(f"SQLite file does not exist: {db_path}")
                    return False
        
        # Test connection universally using SQLAlchemy
        engine = create_engine(uri)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"Connection check failed: {e}")
        return False
