"""Starter profiles discovered from templates/*/contract.json; a profile never authorizes data access or implementation."""
import json

from backend.contracts import ROOT, digest, require

TEMPLATES = tuple(sorted(p.parent.name for p in (ROOT / "templates").glob("*/contract.json")))  # starters are data, not code


def template_path(template_id):
    require(template_id in TEMPLATES, "INVALID_COMMAND", "등록된 고정 템플릿이 필요합니다.", 422)
    return ROOT / "templates" / template_id


def template_contract(template_id):
    return json.loads((template_path(template_id) / "contract.json").read_text())


def plan_support(template_id, spec_id, requests, gaps=()):
    """Per-plan support. `gaps` are unsupported entries computed from the plan itself (e.g. an AC without a check)."""
    template_contract(template_id)
    return dict(template_id=template_id, spec_version_id=spec_id, request_digest=digest(requests),
                implementation_allowed=not gaps, unsupported=list(gaps), external=[])
