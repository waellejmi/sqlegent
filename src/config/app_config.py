from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    EXECUTE_SQL_QUERIES: bool = True
    HUMAN_SQL_REVIEW: bool = True
    MAX_SQL_RETRIES: int = 1
    SHOW_AGENT_GRAPH: bool = False
    SHOW_NODE_HISTORY: bool = True
