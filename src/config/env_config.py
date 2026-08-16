import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class EnvConfig:
    LLM_API_KEY: str = os.getenv("GROQ_API_KEY")
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY")
    LANGSMITH_API_KEY: str = os.getenv("LANGSMITH_API_KEY")
    AZURE_DB_CONNTECTION = os.getenv("AZURE_DB")
