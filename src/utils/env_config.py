import os
import pathlib
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class MyConfig:
    ROOT_DIR: str = pathlib.Path(__file__).resolve().parent.parent.parent
    DB_PATH: str = ROOT_DIR / "data" / "Chinook.db"
    LLM_API_KEY: str = os.getenv("GROQ_API_KEY")
