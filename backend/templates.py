"""Two fixed runtime profiles; neither profile selects or calls a data provider."""
import json

from backend.contracts import ROOT, digest, require

TEMPLATES = ("requests-v1", "cafemap-v1")


def template_path(template_id):
    require(template_id in TEMPLATES, "INVALID_COMMAND", "등록된 고정 템플릿이 필요합니다.", 422)
    return ROOT / "templates" / template_id


def template_contract(template_id):
    return json.loads((template_path(template_id) / "contract.json").read_text())


def plan_support(template_id, spec_id, requests):
    contract = template_contract(template_id)
    blocked = template_id == "cafemap-v1"
    return dict(template_id=template_id, spec_version_id=spec_id, request_digest=digest(requests),
                implementation_allowed=not blocked,
                unsupported=[dict(request_quote=r["content"], reason=contract["support_gap"],
                                  requires=["지도·장소 공급자/무료 자격·쿼터·출처 표시 확정", "필요 키와 위치 동의·격리 경로 준비"])
                             for r in requests] if blocked else [],
                external=[dict(provider=None, purpose="실제 지도·장소 검색과 주변 카페 추천", status="deferred",
                               needs=["free_eligibility", "key", "quota", "attribution", "consent", "isolation"],
                               reason="사용자가 외부 연결은 나중에 결정했습니다. 공급자/키/위치 전송은 미설정입니다.")] if blocked else [])
