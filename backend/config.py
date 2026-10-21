import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database: Path
    token: str
    model: str = ""
    ollama_url: str = "http://127.0.0.1:11434"
    embedding: str = ""
    template_id: str = "requests-v1"

    @classmethod
    def from_env(cls):
        token = os.environ.get("LIFECYCLE_TOKEN") or secrets.token_urlsafe(32)
        if len(token) < 32:
            raise ValueError("LIFECYCLE_TOKEN must be configured with at least 32 characters")
        embedding = os.environ.get("LIFECYCLE_EMBEDDING", "")
        if embedding not in ("", "qwen3-embedding:0.6b"):
            raise ValueError("Only the approved local embedding model is enabled")
        template_id = os.environ.get("LIFECYCLE_TEMPLATE", "requests-v1")
        if template_id not in ("requests-v1", "cafemap-v1"):
            raise ValueError("Select a fixed supported template")
        return cls(Path(os.environ.get("LIFECYCLE_DB", "runtime-data/lifecycle.sqlite3")), token,
                   os.environ.get("LIFECYCLE_MODEL", ""), embedding=embedding, template_id=template_id)
