import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class EnvConfig:
    LLM_API_KEY: str = os.getenv("GROQ_API_KEY")
    LANGSMITH_API_KEY: str = os.getenv("LANGSMITH_API_KEY")
