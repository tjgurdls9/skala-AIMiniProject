"""Fixed runtime profiles; selecting Kakao does not authorize data access or implementation."""
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
                                  requires=["카카오맵 무료 쿼터 배지·유료 API 비활성 확인", "JavaScript/REST API 키·도메인 준비", "위치 동의·신뢰 지도 화면·격리 경로 검증"])
                             for r in requests] if blocked else [],
                external=[dict(provider="kakao", purpose="실제 지도·장소 검색과 주변 카페 추천", status="unconfirmed",
                               needs=["free_eligibility", "key", "quota", "attribution", "consent", "isolation"],
                               reason="사용자가 카카오맵을 선택하고 외부 연결 보류를 해제했습니다. 무료 배지 확인이 어려운 상태이며 키·위치 동의·격리 연결 검증 전에는 호출/구현 승인을 허용하지 않습니다.")] if blocked else [])
