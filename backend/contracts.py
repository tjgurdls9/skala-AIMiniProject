"""Validate only bundled schemas; never resolve model/user supplied references."""

import hashlib
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(r"(?:sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,})")
BASE = "https://lifecycle.invalid/contracts/"
SCHEMAS = {
    name: json.loads((ROOT / "docs/planning" / name).read_text())
    for name in ("protocol.v1.schema.json", "http.v1.schema.json")
}
REGISTRY = Registry().with_resources(
    (BASE + name, Resource.from_contents(schema)) for name, schema in SCHEMAS.items()
)


def validate(name: str, value: object) -> None:
    file = "protocol.v1.schema.json" if name in SCHEMAS["protocol.v1.schema.json"]["$defs"] else "http.v1.schema.json"
    Draft202012Validator(
        {"$ref": BASE + file + "#/$defs/" + name},
        registry=REGISTRY, format_checker=FormatChecker(),
    ).validate(value)


def canonical(value: object) -> str:
    # All digest inputs are JSON values; strings keep their exact Unicode code points.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def plan_inputs():
    files = ["docs/planning/" + name for name in SCHEMAS] + [
        "templates/requests-v1/contract.json", "templates/requests-v1/requirements.lock",
        "infra/Dockerfile.runtime", "infra/Dockerfile.candidate", "infra/checks/validate.py", "infra/checks/security.py"]
    return {name: "sha256:" + hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 409, current_state_version=None):
        self.code, self.message, self.status = code, message, status
        self.current_state_version = current_state_version


def require(condition: bool, code: str, message: str, status: int = 409) -> None:
    if not condition:
        raise DomainError(code, message, status)
