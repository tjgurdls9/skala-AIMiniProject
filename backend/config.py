import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database: Path
    token: str
    model: str = ""
    ollama_url: str = "http://127.0.0.1:11434"

    @classmethod
    def from_env(cls):
        token = os.environ.get("LIFECYCLE_TOKEN", "")
        if len(token) < 32:
            raise ValueError("LIFECYCLE_TOKEN must be configured with at least 32 characters")
        return cls(Path(os.environ.get("LIFECYCLE_DB", "var/lifecycle.sqlite3")), token,
                   os.environ.get("LIFECYCLE_MODEL", ""))
