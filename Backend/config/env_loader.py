# Backend/config/env_loader.py
import os
from typing import Optional

from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(dotenv_path)


def get_env_var(key: str, default: Optional[str] = None) -> str:
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Missing required environment variable: {key}")
    return value
