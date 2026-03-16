from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    EXECUTE_SQL_QUERIES: bool = True
    MAX_SQL_RETRIES: int = 1
