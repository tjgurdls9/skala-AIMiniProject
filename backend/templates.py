"""Fixed runtime profiles; selecting Geoapify does not authorize data access or implementation."""
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
    contract = template_contract(template_id)
    blocked = template_id == "cafemap-v1"
    return dict(template_id=template_id, spec_version_id=spec_id, request_digest=digest(requests),
                implementation_allowed=not blocked and not gaps,
                unsupported=[dict(request_quote=r["content"], reason=contract["support_gap"],
                                  requires=["Geoapify Free 플랜·무료 크레딧/출처 조건 확인", "Geoapify 프로젝트 API 키·비공개 브로커 준비", "위치 동의·신뢰 지도 화면·격리 경로 검증"])
                             for r in requests] if blocked else list(gaps),
                external=[dict(provider="geoapify", purpose="실제 지도·장소 검색과 주변 카페 추천", status="unconfirmed",
                               needs=["free_eligibility", "key", "quota", "attribution", "consent", "isolation"],
                               reason="사용자가 Geoapify Free로 변경했습니다. 프로젝트 Free 플랜/키·출처 표시·위치 동의·격리 연결 검증 전에는 호출/구현 승인을 허용하지 않습니다.")] if blocked else [])
