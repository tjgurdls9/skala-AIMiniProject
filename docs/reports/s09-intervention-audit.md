# S09 개입 목록·공통 기반 부족분·파일 분류 (읽기 전용 감사)

작성: Claude 이어받기 세션, 2026-10-21. 기준 코드: `work/codex-runtime` `9ff9508`. 근거: [execution-boundary.md](../planning/execution-boundary.md), 원본 `docs/handoffs/codex.md` 최상단 인계.
이 문서는 기록만 한다. 삭제·이동·재명명·재실행·외부 호출은 하지 않았고, 기존 실패 원장·커밋·비공개 키는 그대로다. 아래 "근거"는 이 세션이 직접 읽은 파일·DB 행이며, 읽지 못한 것은 "미확인"이라고 적었다.

## 1. S09 판정 (고정)

**개입 있음 / 로컬 모델 자율 개발 수용 미검증.**

| 항목 | 값 |
|---|---|
| 실행 | `846eed645f8245909d72cff799099d0b`, DB `runtime-data/s09-cafemap.sqlite3` (읽기 전용 조회) |
| 상태 | `needs_input`, state_version 10, last_event_seq 18, `spec_version_id` 없음 |
| 사건 | 1–8 첫 기획 시도(문맥 예산 초과), 9–14 기획 v8 생성, 15 변경 요청 저장, 16–18 문맥 예산 초과로 `needs_input` |
| 승인·후보·검토·프리뷰·출시 | grants 0, candidates 0, reviews 0, previews 0, operations 0 |
| 불변 기획 | 이전 spec `8e303310…`은 보존, 그 승인 `0596b983…`은 `invalidated` |

이 실행에서 작업 세션(Codex)이 한 개입:
1. 요청 전송 대행: 사용자의 공급자 정정을 `request_changes(scope=spec)`로 CLI가 전달했다(command_id `9386c64b…`, 202).
2. 정답 성격 코드를 시작 프로젝트에 미리 추가: `templates/cafemap-v1/**`, `infra/checks/validate_cafemap.py`, `backend/{kakao,geoapify,map_access}.py`, `backend/templates.py`의 cafemap 분기.
3. 실행 중 서비스 수정과 재기동(`754165a`, `2dcbd46`, `d6d7c20` 등).
4. 서울시청 좌표 Geoapify geocoding/Places 각 1회를 직접 호출(2026-10-21 06:20:16Z). 개발자 probe이며 모델의 도구 사용이 아니다.

이 개입은 지우지 않고, "ollama 성과"로도 세지 않는다. 문맥 예산 초과 실패는 개입 위에서 일어난 서비스/모델 실패로 남긴다.

## 2. requests-v1 시작 프로젝트와 "합성 문의 완주" 후보 대조

`templates/requests-v1`은 빈 시작 프로젝트가 아니다. `app_backend/main.py`(60줄)에 `/health`, `/api/items` CRUD, SQLite가 있고 `app_frontend/app.js`(16줄)에 문의 화면이 이미 있다. 커밋 `44d8670`(10-20 20:56)에서 처음 들어왔고 `c8bbdd7`에서 수정됐다. 작성자는 작업 세션이다.

후보 저장소 4개(`runtime-data/candidates/<hash>/`, 커밋 메시지는 모두 "Lifecycle Frozen generated candidate")를 템플릿 원본과 파일별로 `diff`했다.

| 후보 | commit | 템플릿과 다른 줄 | 내용 |
|---|---|---|---|
| `33a42615…` | `d834c58` | 0 | 4개 파일 모두 템플릿과 바이트 동일. 모델이 바꾼 것이 없다 |
| `3c1f5a9a…` | `22b13e1` | 0 | 위와 동일. 이 후보를 가진 DB 행은 확인하지 못했다(미확인) |
| `2a1dc0f6…` | `6fd73b3` | `main.py` 9 | 함수 사이 빈 줄 제거만. 동작 변화 없음 |
| `bfdbb4f7…` | `df44da9` | `main.py` 9, `style.css` 2 | `main.py`는 위와 같은 빈 줄 제거. `style.css`는 `button`에 `background-color:#3b82f6;border-radius:4px`, `li`에 `margin-top:12px` 추가, 그리고 기존 `p[role=alert]{color:#a32613}` 규칙이 사라짐 |

- `app_frontend/app.js`와 `index.html`은 4개 후보 모두 템플릿과 동일하다. 문의 화면 전체와 `/api/items` CRUD는 모델이 만든 것이 아니라 템플릿에 있던 것이다.
- 후보 `bfdbb4f7…`의 스타일 변경은 `runtime-data/check_style_change.py`가 `Ollama('qwen3.5:4b')`로 실행해 만든 변경이다(파일에서 확인). 다만 요청 문구("버튼 배경색을 파랑으로 바꾸고 여백을 넓혀주세요")는 스크립트에 박혀 있고, 대상 실행의 기획 승인은 `decided_by: local-operator`(스크립트/개발 승인)다. 모델이 직접 바꾼 줄은 이 CSS 두 줄이 사실상 전부이고, 그 과정에서 오류 문구 색 규칙이 지워진 회귀가 있다. 후속 검증이 이를 잡았는지는 미확인이다.
- 빈 줄 제거가 모델 출력(전체 파일 교체)인지 동결 단계의 부작용인지는 미확인이다.
- `development-check.sqlite3`의 3개 실행은 제목이 "[개발 자체확인·합성] 작은 문의 앱"이고 승인은 스크립트였다. 이들의 "충족/통과"는 개발 점검 자료이며 자율 개발 완주 근거가 아니다.

## 3. 일반 요청을 템플릿 정답 없이 하려면 없는 것 (고치기 전 목록)

| 영역 | 현재 코드 위치 | 상태 | 근거 |
|---|---|---|---|
| 빈 시작 scaffold | `runner/sandbox.py:79-92` `workspace()`, `backend/templates.py:6` | **없음** | 작업 공간은 `templates/<id>/app_backend`·`app_frontend`를 통째로 복사한다. 템플릿은 `requests-v1`, `cafemap-v1` 2개로 고정이고 둘 다 완성 코드를 담는다 |
| 파일 생성·삭제 범위 | `runner/access.py:13` `WRITABLE_FILES`, `runner/sandbox.py:19` `PATCH_SCHEMA`, `runner/mcp_server.py:49` `patch_file` | **없음** | 쓸 수 있는 파일이 4개로 고정이고 `path`가 enum이다. 새 파일 생성·삭제·이름 변경 도구가 없다. 파일당 65536자, 요청당 파일 4개 |
| 명령·빌드·의존성 도구 | `runner/mcp_server.py`(도구: `search_documents`, `specification`, `contract`, `task`, `read_file`, `patch_file`) | **없음** | 모델이 쓸 수 있는 실행/빌드/테스트/설치 도구가 없다. 빌드와 검사는 신뢰 실행기가 모델 밖에서 한다. 템플릿 계약도 "No package changes"다(`templates/requests-v1/contract.json`) |
| 요청별 검증 기준 생성 | `infra/checks/validate.py`, `runner/review.py:42`, `backend/contracts.py:46-48` | **없음** | 검증기는 `/api/items`를 직접 두드리는 6개 점검(`health`, `create`, `list`, `update`, `invalid_input`, `persistent_storage`)이 하드코딩이다. 다른 템플릿은 별도 스크립트(`validate_cafemap.py`)를 코드에서 골라 쓴다. 모델이 만든 AC는 글일 뿐이고 `runner/pipeline.py:182`는 근거를 `tool_evidence.checks` 키로 제한하므로, 고정 점검에 없는 AC는 `not_run`이 된다 |
| 문맥 | `runner/context.py:8-9`(BUDGET 14000, FRAGMENT_BYTES 2400), `runner/context.py:65-67`, `runner/worker.py:118` | **결함 있음** | 승인된 적 없는 최신 spec이 planner에게 `approved_spec`으로 실린다. S09 `needs_input`의 후보 원인(2단계에서 재현·수정 대상). 예산 확대·정정 근거 절단은 하지 않는다 |
| 독립 검토 | `runner/review.py`, `runner/pipeline.py:180-182` | 부분 | validator·security 두 역할의 독립 검토는 있다. 그러나 점검 항목이 템플릿에 묶여 있어 임의 요청에는 검증할 대상이 없다 |
| 복구 | `runner/release.py:97`, `runner/release.py:72` | 부분 | 첫 출시 복구는 컨테이너를 내리고 볼륨을 보존하는 방식이고 어댑터 구성은 있다. 실제 출시 실행은 비활성(`ReleaseView.enabled=false`)이며, 프리뷰 프록시 명령 검사에 `cafemap-v1` 분기가 섞여 있다. 실제 출시·복구 수용은 미확인 |
| 템플릿 분기 | `runner/pipeline.py:341`, `runner/review.py:42`, `runner/sandbox.py:87`, `runner/release.py:72`, `backend/contracts.py:46-48`, `backend/config.py:25`, `backend/api.py:130,135`, `infra/checks/preview.py:47-49` | **하드코딩** | 공통 실행기 안에 `if template_id == "cafemap-v1"` 분기가 8곳 이상 있다. 요청별 정답과 공통 기반이 같은 파일에 섞여 있다 |

## 4. 파일·커밋 분류표

분류: **공통 서비스 / 요청별 정답 코드 / 독립 평가 도구 / 수동 시험**. 삭제·이동·재명명은 하지 않았다. "제안"은 분리 후보이며 승인 전에는 실행하지 않는다.

| 대상 | 커밋 | 분류 | 설명·분리 제안 |
|---|---|---|---|
| `templates/cafemap-v1/**` | `b40e292`, `4f84826`, `d6d7c20` | 요청별 정답 코드 | 카공지도 `/api/map/*`, 설정 DB, 지도 화면. 모델이 만들 대상을 미리 구현했다 |
| `templates/requests-v1/app_backend`, `app_frontend/{app.js,index.html,style.css}` | `44d8670`, `c8bbdd7` | 요청별 정답 코드 | 문의 앱 완성본. "빈 scaffold"가 아니다 |
| `templates/requests-v1/app_frontend/vendor/**`, `requirements.{txt,lock}` | `44d8670` | 공통 서비스 | 고정 의존성(Vue ESM, FastAPI 잠금). 생성 앱이 공통으로 쓰는 바닥. 제안: 앱 코드와 디렉터리를 분리 |
| `templates/*/contract.json` | 위 커밋 | 혼합 | 엔드포인트·protected_checks·구현 작업 분해가 요청별이다. 공통 필드(제한, 작업 종류)는 서비스 몫. 제안: 요청별 필드를 템플릿 매니페스트로 분리 |
| `infra/checks/validate.py` | `44d8670` | 독립 평가 도구 | 문의 앱 전용 점검. 작성자는 작업 세션이라 "모델이 만든 AC"가 아니라 "개발자가 고른 AC" |
| `infra/checks/validate_cafemap.py` | `b40e292`(35줄) | 독립 평가 도구 | 카공지도 전용. 같은 커밋에서 점검 대상 템플릿도 함께 작성돼 독립성이 약하다 |
| `infra/checks/security.py`, `preview.py`(공통부) | `44d8670` | 공통 서비스 | 후보 이미지 보안 검사, 프리뷰 프록시 공통부 |
| `infra/checks/preview.py:47-49` | `b40e292` | 요청별 정답 코드 | `/api/map/` 가짜 응답 분기 |
| `backend/map_access.py` | `d6d7c20` | 공통 서비스(후보) | 600 권한 키 파일 읽기, 고정 호스트/경로, 일 한도 200, 429 당일 중단, 응답 128KiB 상한. 범용 외부 호출 보호에 가깝지만 `ENDPOINTS`가 카카오/Geoapify 전용이다. 제안: 공급자 허용표를 분리 |
| `backend/geoapify.py` | `d6d7c20` | 요청별 정답 코드 | 카페/인터넷 태그 검색 질의·후보 선택. 생성 앱의 검색 기능이다 |
| `backend/kakao.py`, `backend/tests/test_kakao.py` | `4f84826`, `d6d7c20` | 요청별 정답 코드 | 보존. 사용하지 않는 공급자 경로 |
| `backend/tests/test_geoapify.py` | `d6d7c20` | 독립 평가 도구 | 합성 검사 3개. 모델 성과 아님 |
| `backend/templates.py` | `b40e292`→`d6d7c20` | 혼합 | `plan_support()`의 `blocked = template_id == "cafemap-v1"`와 Geoapify 문구가 요청별 정답과 결합. 공통 부분은 `template_path`/`template_contract` |
| `runner/pipeline.py:341` 외 템플릿 분기 8곳 | `b40e292` 등 | 혼합 | 공통 실행기 안의 요청별 분기. 제안: `contract.json`의 데이터(검증 스크립트, 추가 복사 경로, 프록시 인자)로 치환 |
| `runtime-data/check_*.py`, `run_*_check.py`, `continue_pipeline_check.py`, `development-*.json`, `style-result.json` | 개발 중 | 수동 시험 | 스크립트가 요청·승인을 공급했다(`decided_by: local-operator`) |
| `runtime-data/geoapify-public-probe-*.json`, `geoapify-usage.sqlite3`, `geoapify-user-correction-*.json` | `d6d7c20` 시기 | 수동 시험 | 서울시청 probe와 사용자 정정 대행 기록. 키·사용량은 Git 제외 |
| 정정 대행 `request_changes`(command_id `9386c64b…`) | — | 수동 시험 | CLI가 전송한 사실을 기록한다 |

## 4-1. 관제 추가 감사: 계약 enum과 서버가 만드는 과제 전용 문구

계약은 바꾸지 않았다. 결정은 이 감사 결과와 함께 관제가 한다.

**CR-C16 초안 대조** (프론트 인계 `docs/handoffs/claude.md` "재개 6", 사무실 `a00b5d2`)
- 확인: `docs/planning/http.v1.schema.json:54`는 `Runtime.template_id`를 `{"enum": ["requests-v1","cafemap-v1"]}`로, 같은 파일 75–76행은 `PlanSupport.template_id`를 같은 두 값으로 제한한다. `docs/planning/contracts.md:169`도 "고정 requests-v1/cafemap-v1"로 적는다. 서버 쪽 근거는 `backend/templates.py:6`(`TEMPLATES`), `backend/config.py:25`의 같은 두 값 검사다. 과제 이름이 공통 계약에 들어 있다는 지적은 사실이다.
- 영향: 템플릿을 하나 추가·교체하면 계약, 생성 타입, 서버 검사 3곳을 동시에 바꿔야 한다. 이는 3절의 "빈 scaffold 없음"과 같은 뿌리다(시작 프로젝트가 데이터가 아니라 코드에 박혀 있다).
- 이 감사의 의견: 패턴 문자열로 느슨하게 하는 안은 계약 쪽으로는 타당하다. 다만 서버가 임의 ID를 받으려면 `backend/templates.py`/`config.py`의 목록 검사와 `contract.json` 로딩도 같이 일반화해야 하므로, 계약만 먼저 풀면 서버가 여전히 두 값만 받는 불일치가 생긴다. 한 번에 정할 것을 권한다. 미결정.

**서버가 만드는 과제 전용 문구가 공통 화면에 그대로 나가는가: 나간다.**

| 서버 위치 | 문구(요약) | 노출 경로 |
|---|---|---|
| `backend/api.py:135` `Runtime.reasons` | "카공지도 프로필: Geoapify Free 선택, 프로젝트 플랜·키·격리 연결은 미확인입니다…" / "작은 문의 앱 템플릿만 지원합니다…" | `reasons`는 항상 마지막에 프로필 문장이 붙는다. 실행 가능(`live_available=true`)일 때도 붙으므로 `reasons`가 "막는 이유"와 "프로필 안내"를 섞는다. 프론트 인계 재개 6은 서버 `reasons`를 시작 화면에 그대로 붙인다고 적었다(`d72e888`은 LIVE 불가일 때 첫 사유 중복만 정리했다). 이 문장은 사용자가 요청한 내용과 무관하게 모든 사용자에게 보인다 |
| `backend/templates.py:19-27` `plan_support()` | `requires`: "Geoapify Free 플랜·무료 크레딧/출처 조건 확인", "Geoapify 프로젝트 API 키·비공개 브로커 준비", "위치 동의·신뢰 지도 화면·격리 경로 검증"; `external.reason`: "사용자가 Geoapify Free로 변경했습니다…" | 기획 승인 화면의 지원 구역이 서버 문장을 그대로 표시한다(프론트 인계: 문장은 서버 값 그대로). 서버 문장이 곧 화면 문장이다 |
| `templates/cafemap-v1/contract.json:27` `support_gap` | "…한국 카페 검색 품질과 조용함·콘센트·장시간 이용 적합성은 확인되지 않았습니다." | `plan_support()`가 `unsupported[].reason`으로 넣는다 |
| `backend/templates.py:20` | `blocked = template_id == "cafemap-v1"` | 승인 가능 여부(`implementation_allowed`)가 템플릿 이름 비교로 정해진다. 요청 내용 평가가 아니다 |

판단: 프론트가 과제 이름을 만들지 않게 고친 `2ee4a30`은 화면 코드 쪽만 중립화했다. 같은 문구가 서버에서 만들어져 계약을 통해 그대로 나간다. 서버 문구가 요청 내용(예: "카공지도")이 아니라 **운영자가 고른 템플릿 ID**에서 나온다는 점이 핵심이다. 사용자가 다른 요청을 입력해도 cafemap 프로필이면 지도 공급자 공백이 붙는다. 이 판정은 코드 읽기이며, 실서버 응답은 이번 세션에서 띄우지 않아 직접 확인하지 못했다(미확인).

## 5. 다음 단계와 미확인

- 2단계(문맥 `latest_spec`/`approved_spec` 혼용): 회귀 테스트 `test_unapproved_prior_plan_is_never_sent_as_approved_spec`를 먼저 추가해 RED(73개 중 1개 실패)를 확인한 뒤 `runner/worker.py:claim`을 고쳤다. 승인 여부를 한 번만 계산해 구현 게이트와 `latest_spec` 라벨에 같이 쓰고, 승인되지 않은 초안은 `latest_spec=None`으로 싣는다. 이 때문에 기존 `test_runtime.py`의 재기획 테스트가 단언하던 "승인되지 않은 이전 기획이 `latest_spec`에 실린다"를 `assertIsNone`으로 뒤집었다(의도된 의미 변경). GREEN은 73개 통과. 예산 상수와 정정 근거는 건드리지 않았다. 이 수정이 S09의 문맥 예산 초과를 실제로 해소하는지는 새 run 없이는 **미확인**이다. 과거 S09 실행의 평가와는 분리한다.
- 3단계(새 run)는 보류다. 고정 조건표(서비스 커밋, 모델, 시작 프로젝트, 허용 도구, 기준)를 관제에 보낸 뒤에만 진행한다. 사용자 기획 승인은 합성하지 않는다.
- 미확인: 후보 `3c1f5a9a…`의 소속 실행, 빈 줄 제거의 발생 지점(모델 출력인지 동결인지), `bfdbb4f7…`의 `p[role=alert]` 규칙 삭제를 검증이 놓쳤는지, `kakao.py`/`geoapify.py`의 모든 줄(이 감사는 호출 관계와 분류만 보았다), 실제 출시·복구, Firefox/Safari 등 이 감사 범위 밖 항목.
