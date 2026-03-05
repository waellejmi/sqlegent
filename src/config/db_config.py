import pathlib
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class DBConfig:
    ROOT_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent.parent.parent
    DB_PATH: pathlib.Path = ROOT_DIR / "data" / "Chinook.db"
