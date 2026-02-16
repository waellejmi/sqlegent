import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class MyConfig:
    LLM_API_KEY: str = os.getenv("GROQ_API_KEY")
