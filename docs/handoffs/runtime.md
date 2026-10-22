# 런타임 세션 인계 (F0–F6 완료. 실서버 전체 흐름 확인 전)

첫 작성은 F5 직후(a836b3b)이고, 교대한 두 번째 세션이 F4d·F6을 끝내고 §10을 더했다. 런타임 worktree `.worktrees/codex-runtime`, 브랜치 `work/codex-runtime`. 이 문서 하나로 이어받을 수 있게 썼다. 관제탑 세션 이름은 `skala-aiminiproject-a7`(보고는 SendMessage로 이 이름에 보낸다).

## 1. 현재 상태

| 항목 | 값 |
|---|---|
| HEAD | `969c1b4` (F5 2단계). 이 인계 문서 커밋이 그 위에 한 개 더 있다 |
| 테스트 | `backend/.venv/bin/python -m unittest discover -s backend/tests` → 277건 OK |
| 커버리지 | 총 88% (`coverage run --branch --source=runner,backend --omit='backend/tests/*' -m unittest discover -s backend/tests`). `runner/review.py` 78%(80% 미달), `runner/sandbox.py` 53%, `runner/mcp_server.py` 69%, `runner/model.py` 62% |
| 작업 트리 | 인계 커밋 뒤 깨끗해야 한다. `runtime-data/`는 git 제외 |
| 실행 중 프로세스 | 없음(Ollama·컨테이너·API·worker 모두 이 세션이 띄운 것 없음, 인계 직전 확인) |

## 2. 완료한 일 (F0–F5)

한 줄씩, 오래된 것부터.

- `5263015` F0 문맥 유형별 테스트 고정 (짧은 요청, 긴 원문, 정정 체인, 재기획)
- `224ad76`, `f9b074e` 승인 안 된 초안은 `latest_spec`로 보내지 않고 `prior_draft` 슬롯으로 따로 싣는다
- `98ad1bd`, `ecc7259` S09 개입 감사 보고서 (`docs/reports/s09-intervention-audit.md`)
- `fdac850`, `66c4481`, `8c34d21` 공통 기반 설계 (`docs/planning/agentic-foundation-design.md`, R01–R30, D1–D7)
- `37050e9` F1 원장 도구·작업 공간·명령 정책 (ToolBox, Workspace, DockerExecutor)
- `76147c6` 계약: 일반 template id(CR-C16), 계획 확장(CR-C17)
- `9943e3b`, `c9511c0`, `05415c2` F2 작업 분해·점검 명세 검증, 점검 기계 판정, 모델 기획 확장(대안·작업 분해·AC별 점검)
- `dc58df4` 실제 컨테이너 격리 검증 (`infra/verify_isolation.py`)
- `22ebe5c`, `4a740b6`, `35c23c8`, `385e931` F3 서버 판정 RED→GREEN 게이트, 빌더 루프, 워커 연결
- `378a7ec` F4a 승인을 도구 정책에 결속, 허용 의존성 범위 전달
- `79496cc`, `c2890d5`, `a66ffc9`, `a66af69`, `e1b545b`, `11393b5`, `0af2fe7` 실모델(qwen3.5:4b) 빌더 루프 스모크와 그에 따른 보강
- `faa1db3` F4b 작업별 커밋과 일반 후보 고정(`runner/candidate.py`)
- `d09b676`, `5b2a6e3`, `6d012d0`, `6995dfa` 16GB 멈춤 이후 메모리 감시자, 모델 비교 보고서, 실패 요약
- `bf5f6f2` F4c 독립 검증이 승인된 점검 명세를 후보 이미지에서 실행
- `c49e514`, `55b6551` C9(사람 확인 승인) 조건 문서화, 실제 컨테이너 검증기 점검
- `db1300f` F4d 계약: `AcceptanceTarget`(gate `acceptance`), `ReleaseTarget.acceptance_approval_id`
  - `docs/planning/http.v1.schema.json` sha256 `c30058eaf8ca863820dd431c240494fef8e204af3a853a3ef38151292af2fd47`
  - `docs/planning/protocol.v1.schema.json` sha256 `8dc0d7eb71d1f9c36342526d36f17c3083cdde7346c8e2e00bd7025cd0e9d8f3`
- `3f7da18` F5 1단계: 카공지도 시작 프로젝트·Kakao/Geoapify 어댑터·`validate_cafemap.py` 삭제, 범용 브로커 `backend/external_access.py`
- `969c1b4` F5 2단계: `templates/requests-v1/**`, `infra/checks/validate.py`, `infra/Dockerfile.candidate`, 고정 템플릿 빌더 경로 삭제. 시작 프로젝트는 `blank-v1` 하나이며 기본값

사용자 결정으로 D5는 "격리"에서 "삭제"로 바뀌었다. 되돌림은 git 이력으로 한다(근거 커밋 `b40e292`, `4f84826`, `d6d7c20`).

## 3. 문서 위치

| 문서 | 내용 |
|---|---|
| `docs/planning/agentic-foundation-design.md` | 설계. §3 AC 충족 경로, §4 설계, §6 구축 완료 조건 C1–C10, §8 F0–F6 테스트 계획, §9 결정 D1–D7 |
| `docs/reports/s09-intervention-audit.md` | S09는 "개입 있음 / 자율 수용 미검증". 개발자가 쓴 코드를 Ollama 성과로 세지 않는다 |
| `docs/reports/builder-loop-smoke-20261021.md` | 실모델 빌더 루프 스모크(개발 점검, 수용 시험 아님) |
| `docs/reports/model-comparison-20261021.md` | qwen3.5:4b 대 qwen2.5-coder:7b, deepseek-coder:6.7b, 메모리 측정 |
| `docs/reports/memory-incident-20261021.md` | 16GB 머신 멈춤 사고와 시작 조건·감시자 |
| `docs/reports/docker-isolation-check.md` | 실제 Docker 격리 15개 점검 결과 |
| `docs/reports/candidate-review-check.md` | 후보 독립 검증 실컨테이너 10개 점검 결과 |
| `docs/handoffs/control-tower.md`, `claude-control-tower.md` | 관제탑 인계 |

## 4. 남은 일

### 4.1 F4d 서버 구현 (계약은 `db1300f`로 완료)
- 검증기·보안 통과 뒤 `manual_acceptance`가 있으면 `AcceptanceTarget` 승인을 만든다(상태 `preview_ready`). 대상은 후보(커밋·이미지 digest)와 AC id에 결속
- 검증기 판정 `pass`는 "자동 점검 대상 AC가 모두 충족"을 뜻하고 `manual_pending`이 본문에 남는다. 사람 확인이 검증기의 `not_run`을 `met`으로 바꾸지 않는다
- `decide`가 gate `acceptance`를 처리한다(approve, reject→`needs_input`). 새 후보·새 명세·구현 변경 시 승인은 무효
- `ReleaseTarget.acceptance_approval_id`가 없으면 출시 대상을 만들 수 없다. 관련 코드는 `runner/release.py` 약 133·157·180행, `backend/store.py`의 `decide`
- 테스트는 RED 출력을 먼저 남긴다

### 4.2 F6 통합과 개입 감지
- 가짜 모델로 범용 소형 요청 하나가 계획 → 대안·점검 → 기획 승인 → 빌더 → 검증·보안 → 프리뷰 → 사람 확인 승인 → 배포 승인 대상까지 통과하는 통합 테스트(C4). 승인은 테스트 픽스처 조작이며 실제 사용자 승인으로 세지 않는다
- 원장 밖 작업 공간 변경이 있으면 run에 개입 표시
- 공통 코드 중립성 정적 테스트는 이미 있다 (`backend/tests/test_task_neutrality.py`)

### 4.3 기타
- `runner/review.py` 커버리지를 80% 이상으로(현재 78%)
- `Pipeline.release`의 프리뷰 헬스 확인이 `/health`와 `{"status":"ok"}`로 고정돼 있다(`runner/pipeline.py`). 앱 선언 `lifecycle.app.json`의 `health` 경로를 쓰도록 일반화해야 한다. 지금은 앱이 그 규약을 따라야만 프리뷰가 뜬다
- 미사용 import 몇 개가 남아 있다(`runner/builder_loop.py`, `plan_extras.py`, `tools.py`, `worker.py`, `infra/checks/security.py`). 이 세션이 만든 것은 아니다
- `docs/planning/contracts.md`와 `backend/README.md`에는 카공지도·requests-v1 이전 기록이 일부 남아 있다(역사 기록). 필요하면 정리
- `infra/Dockerfile.runtime`이 프리뷰 프록시용 순수 Python 이미지로 바뀌었다. 실제 프리뷰 전에 `python -m runner.sandbox prepare`를 다시 해야 한다. `runtime-data/runtime-image.json`은 일부러 건드리지 않았고 입력 불일치로 "다시 준비하세요"가 나온다
- 이 세션에서는 새 구조(blank-v1만)로 실제 Docker·Ollama 전체 흐름을 돌려보지 않았다. 모델·도구 스모크는 F3·F4 단계의 개별 점검뿐이다(미확인)

### 4.4 구축 완료 조건 C1–C10 현황 (설계 §6)

| 조건 | 현황 |
|---|---|
| C1 부족분 1–7 | 대안·작업 분해·점검·RED/GREEN·독립 검증은 구현. 사람 확인 승인(F4d)과 통합 테스트(F6)가 남음 |
| C2 F0–F6 RED→GREEN, 커버리지 80% | F0–F5 완료, 총 88%. F4d·F6 남음, `review.py`는 78% |
| C3 이름 없음(정적) | 완료. `test_task_neutrality`가 cafemap·kakao·geoapify·requests-v1·구 빌더 기호를 금지 |
| C4 가짜 모델 통합 | 미완료 (F6) |
| C5 실모델 스모크 | 부분. F3·F4 개별 스모크만 있고 전체 흐름은 아직 |
| C6 독립 코드·보안 리뷰 | 미실시. F4d·F6 이후 `ecc:code-reviewer`·`security-reviewer`로 |
| C7 AC 추적표 증거 연결 | 미갱신 |
| C8 S09 DB 불변 | `runtime-data`의 DB는 열기만 했다. 복사본으로만 읽었다. 해시 비교는 아직 안 했다(최초 해시를 기록하지 않았으므로 새 세션이 지금 해시를 기록하고 끝에 다시 비교) |
| C9 사람 확인 승인 | 계약만 완료, 서버 미구현 (F4d) |
| C10 관제탑·사용자 확인 | 미완료 |

## 5. 지켜야 할 규칙

- 작업 세션은 앱 코드·명령·검증 기준을 공급하지 않는다. 그런 것은 모델이 만들고, 서비스는 검증만 한다
- 카공지도는 구축 완료(C1–C10) 뒤에만 시험 입력으로 쓴다. 서비스를 시험 입력에 맞추지 않는다
- RED 출력(실패하는 테스트)을 남긴 뒤 구현한다. ECC 우선: TDD, 커버리지 80%, 불변 스타일
- 실모델(Ollama) 실행 전에 메모리 시작 조건과 감시자를 쓴다 (`infra/dev_checks/memory_guard.py`: 여유 15% 미만 또는 스왑 4096MB 초과가 연속 두 번이면 자기 Ollama와 `lifecycle-` 컨테이너만 중지, 시작은 여유 40% 이상·스왑 2048MB 미만일 때). 한 번에 모델 하나, 작업 하나
- Ollama와 컨테이너는 자기가 띄운 프로세스만 다룬다. 운영 모델은 `qwen3.5:4b`로 유지
- 사용자 결정(기획 승인·배포 승인·사람 확인·모델 교체·통합 merge)을 합성하지 않는다
- 도구·권한 거부를 우회하지 않는다. 막히면 미확인으로 남기고 보고한다
- 서브 에이전트를 띄우기 전에 목적·모델·추론 강도를 사용자에게 먼저 묻는다(전역 CLAUDE.md)
- 비밀값(키, `runtime-data/secrets/**`)은 출력·로그·커밋에 넣지 않는다
- push와 배포는 하지 않는다. `frontend/**`는 사무실 세션 소유다
- 삭제 전에는 대상 목록·되돌림 방법을 먼저 적고 정확한 경로만 지운다(와일드카드 rm 금지, 훅이 막는다)
- 실모델 실행은 범용 소형 요청만 쓰고 관제에 먼저 알린다

## 6. 사용자 요청 (관제 전달)

"런타임·관제에서 전체 흐름이 도착하면 실시간으로 돌아가는 것을 같이 확인하고 진행하자." F4d 서버까지 끝나 `blank-v1` 경로로 한 번에 돌릴 수 있게 되면 관제에 먼저 알린다. 돌릴 흐름은 기획 → 대안·점검 → 기획 승인 → 빌더 → 검증·보안 → 프리뷰 → 사람 확인 승인 → 배포 승인 대상까지다. 그 전에 실서버 API·worker를 혼자 띄워 사용자 결정을 대신 내리지 않는다. 요청은 범용 소형 요청이다.

## 7. 통합 대기 프론트 커밋 (사용자 허용 필요, 지금 시도하지 않음)

- 사무실 worktree `.worktrees/claude-office` HEAD `9b502bd`
- 대기 목록: `4fc4084`, `5addfd2`, `d68a4da`, `e5016e5`, `b412161`, `cabe631`, `e6d14c6`, `6ecfb65`(db1300f 채택), `4c6f8db`, `9b502bd`
- 관제탑이 338/338 통과를 확인했다. 통합 시점은 관제탑이 F6 직전이나 실서버 확인 전에 묶어서 요청한다. 이미 허용받아 합친 것은 `9c1492e`(merge `6238049`)

## 8. 보존 대상

- `runtime-data/` 전체: DB(`s09-cafemap.sqlite3`, `s09-keyless-2dcbd46.sqlite3`, `development-check.sqlite3` 등), 실패 원장, `secrets/**`, 이미지 기록
- Docker 볼륨: 옛 `lifecycle-*-data` 11개(10-20 기록)는 건드리지 않는다
- 내려받은 모델 `qwen2.5-coder:7b`, `deepseek-coder:6.7b`는 지우지 않는다(삭제는 사용자 결정). Ollama 기본 모델은 바꾸지 않는다
- 제출 tar, 감사·관찰 문서
- 옛 run(S09 포함)은 읽기 전용으로 열린다. `backend/tests/test_legacy_runs.py`가 이를 확인한다. 시작 프로젝트 기록이 없는 옛 run은 읽기만 되고 이어서 실행할 수 없다

## 9. 미확인·주의

- 새 구조의 전체 흐름(실Docker, 실Ollama)은 아직 한 번도 돌리지 않았다
- `worker.finish`는 계획 확장(extras) 없이 직접 호출하면 작업이 없는 기획을 만든다. 정상 경로(`tick`)는 항상 확장을 만든다. 테스트가 직접 호출할 때만 쓰인다
- 모든 변경 요청(`request_changes`)은 이제 재기획으로 간다(스타일 변경 지름길 삭제). 소규모 수정에 승인을 재사용하는 방식은 설계에 없다
- `.worktrees/codex-runtime/runtime-data/runtime-image.json`은 구 Dockerfile 해시를 담고 있어 준비 전까지 `Sandbox.runtime()`이 실패한다
- 실서버 응답은 이 세션에서 띄워 보지 않았다

## 10. 교대 후 두 번째 세션이 한 일 (F4d 서버, F6, 커버리지)

| 커밋 | 내용 |
|---|---|
| `5519f3b` | F4d 서버(CR-C18). validator 판정은 자동 점검 AC만으로 정하고 `manual_acceptance` AC는 `not_run`으로 두며 보고서 본문에 `manual_pending`을 적는다. 프리뷰 공개(`Pipeline.release`) 때 후보 커밋·이미지·AC id·validator 보고서에 결속된 `AcceptanceTarget` 승인 1개를 `pending`으로 만든다(재실행해도 중복 없음). `decide`가 gate `acceptance`를 처리한다(approve는 판정 불변, reject는 의견 원문 보존 후 `needs_input`, 현재 후보·두 PASS 보고서와 다르면 `STALE_APPROVAL`). 새 후보·재빌드 재개·변경 요청이 pending/approved 승인을 `invalidated`로 만든다(거절은 유지). `manual_acceptance`가 있으면 `ReleaseTarget.acceptance_approval_id`가 `prepare`와 `authorize` 양쪽에서 필수. `Pipeline.release` 헬스 확인은 앱이 선언한 `health` 경로(200~399)를 쓴다 |
| `c1aaec2` | F6. `runner/intervention.py`와 `Pipeline.build`: 도구 원장(write/delete/move 성공 기록)이 설명하지 못하는 작업 공간 변경, 작업 사이의 손 편집, 작업 사이에 바뀐 git 이력을 해당 작업의 `code_diff` 본문 `interventions`와 `warning` 사건에 남긴다(실행은 막지 않음). `Store.interventions(run_id)`로 조회. 명령(`run_tests` 등)을 쓴 작업은 만든 파일을 원장으로 귀속할 수 없어 작업 사이 편집만 잡는다(코드에 `ponytail:` 한계 표기). `backend/tests/test_full_flow.py`: 가짜 모델로 범용 소형 요청 하나가 계획(대안·작업 분해·AC별 점검·사람 확인 AC) → 기획 승인 → 모델 빌드(원장) → validator·security → 프리뷰 → 사람 확인 승인까지 간다. 승인은 테스트 픽스처 조작이며 실제 사용자 승인이 아니다 |
| `1367e90` | `runner/review.py` 커버리지 78% → 95%(보안 검토기·스캐너 준비·명령 점검 시간 초과 특성 테스트, 새 동작 없음) |

- 테스트 317건 OK, 총 커버리지 89%.
- 미사용 import 6개 정리(builder_loop, plan_extras 2개, tools, worker, infra/checks/security). `worker.py`와 `security.py`는 `plan_inputs` 해시 대상이라 이전에 만든 기획의 승인은 낡은 것으로 보인다(살아 있는 기획 없음, S09는 읽기 전용).
- `python -m runner.sandbox prepare`를 실행했다. 새 프리뷰 프록시 이미지 `sha256:d08b7756…c269c0`가 `runtime-data/runtime-image.json`에 기록됐다(`status`로 확인). 옛 기록은 `runtime-data/runtime-image.before-f5.json`에 복사해 뒀다. 옛 `lifecycle-runtime:*` 이미지는 지우지 않았다.
- C8: 이 세션이 시작할 때 읽기 전용으로 기록한 해시(끝에 다시 비교할 것)
  - `s09-cafemap.sqlite3` `6a738d7ee1d4b9e83d7fc10a61f527d343f11f77727feb811b23584288855bc4`
  - `s09-keyless-2dcbd46.sqlite3` `8ec703d4888d9f9cc8eb63d7b6ea9145c27d5dd37f88a68779c138cf4286310e`
  - `development-check.sqlite3` `514e65ab256039747bb7aee696e7eb2c5f71203fb726b0a3677f219fb138fbce`

### 남은 일과 알려진 한계

- **배포 대상은 만들어지지 않는다.** 워커가 만드는 기획의 `repository`/`deployment`는 항상 null이라 실서버 run에서는 `ReleaseOperations.prepare`가 STALE_APPROVAL로 거절된다. 저장소·환경 선택은 사용자·운영자 결정(S10)이므로 설정 경로를 만들지 않았다. 흐름은 모든 승인(기획, 사람 확인)과 두 PASS 보고서를 갖춘 `preview_ready`에서 멈춘다. `test_full_flow`가 이를 명시적으로 검증한다.
- `DockerEnvironment.observe`(배포 환경 관찰)는 아직 `/health`와 `{"status":"ok"}`로 고정돼 있다. 배포가 연결될 때 매니페스트에 앱이 선언한 health 경로를 담아야 한다.
- C6 독립 코드·보안 리뷰는 §11에서 진행한다.
- C7 AC 추적표 증거 연결, C10 관제·사용자 확인은 남았다. 프론트 대기 커밋(§7)은 아래 §11에서 통합했다.
- 실서버 전체 흐름(실 Ollama·실 Docker)은 아직 한 번도 돌리지 않았다. 돌릴 때 필요한 것: `LIFECYCLE_PYTHON_IMAGE`, `LIFECYCLE_NODE_IMAGE`(digest 고정, 로컬에 `python:3.13-slim`, `node:24-slim` 이미지가 있다), `LIFECYCLE_MODEL=qwen3.5:4b`, `LIFECYCLE_DB`(별도 새 파일), 메모리 시작 조건과 감시자. 관제·사용자와 함께 시작한다.

## 11. 통합·push·리뷰 상태 (사용자 결정 "일단 머지 커밋 푸시 해. 문서들 갱신하고. 코드리뷰 다 돌면 그 때 다시 물어봐", 관제 전달)

- **merge**: `work/claude-office`를 `b525f81`까지 병합했다(`2df120c`). 충돌 없음. 계약 파일은 런타임 쪽 그대로이며 sha256이 `http.v1` `c30058ea…` / `protocol.v1` `8dc0d7eb…`로 db1300f와 같다. `npm run gen:types` 결과에 diff 없음.
- **merge 뒤 확인**: 백엔드 317건 OK, 프론트 vitest 338건 OK(21개 파일), `vite build` 통과.
- **관제 문서 채택**: `docs/handoffs/control-tower.md`(sha256 `53f178d0…`)와 `claude-control-tower.md`(`1bf3215e…`)를 원본에서 바이트 그대로 복사했다. 관제 소유이며 이 브랜치에서 수정하지 않는다.
- **push**: 이 문서를 포함한 커밋 뒤에 `origin/work/codex-runtime`, `origin/work/claude-office`로 올린다. `main`은 건드리지 않는다. 결과(원격 해시)는 관제 보고에 적었다.
- **리뷰(C6)**: 독립 리뷰 1회(sonnet, high), 대상은 6cc9a0b 이후 `backend/`·`runner/`·`infra/`. 원문은 `docs/reports/code-review-f0-f6.md`. CRITICAL/HIGH는 고치지 않고 목록만 관제에 보고했다. 수정 여부는 사용자 결정이다.

## 12. 리뷰 수정과 첫 실서버 run (2026-10-22)

- **수정 커밋**: `9f4b375`(H-4·H-5), `2beae84`(H-1·H-2·H-3·SECRET 경계), 그 뒤 재검토 N-1(보안 검사 `sk-` 단어 경계)·N-2(`node --test`의 `ℹ pass N` 인식) 수정. 재검토 원문은 `docs/reports/code-review-f0-f6.md`.
- **마감으로 수정하지 않은 것**(사유: 제출 마감): 리뷰 MEDIUM 중 grant 900초 만료 표시, 앱 미기동 판정, 비UTF-8 파일의 보안 스캐너 크래시, 재시도 task의 거짓 개입 표시·첫 task 사각지대, 예외 진단 로그, `/data` 볼륨 쓰기 권한, LOW 8건. 재검토 N-3(설치 잠금 파일이 개입으로 표시), N-4(테스트가 하나도 안 돌아도 exit≠0이면 RED), N-5(`verify_isolation.py` 낡음), N-6(접두사 재충돌, 거부는 됨), N-7(요약이 64KB에 잘리면 개수 못 읽음). 알려진 문구 문제: `/api/runtime`의 `reasons`에 옛 문구 "작은 문의 앱 템플릿만 지원합니다…"가 남아 있다(`backend/api.py:134`).
- **첫 실서버 run `67f60a`**(DB `runtime-data/live-20261022.sqlite3`, 보존): 사용자가 화면에서 "할 일을 추가하고 완료 표시할 수 있는 간단한 웹 앱을 만들어 줘"를 입력했다. 기획(AC 2개)과 아이디어 대안 3개까지 성공했고, 작업 분해(work_plan)에서 `qwen3.5:4b`가 `ai_data` 영역을 작업에도 생략 이유에도 넣지 않는 오류를 서버가 돌려줘도 반복해 `needs_input`(v2)으로 멈췄다. 판정은 **모델 판단 실패**(서비스 결함 아님). 이 run에는 명령을 보내지 않았다. 모델의 원문 응답이 원장에 남지 않는 기록 약점이 있다(후속 과제). 이 run은 빌더·검증·프리뷰 단계에 도달하지 못했다.
- 이 run 뒤에 서비스 결함 N-1·N-2를 고치고(실행 경계 절차: 해당 run 평가 종료·보존 → 수정 커밋 → 새 run) API와 worker만 재시작해 새 run을 받는다.

## 13. 다음 세션 시작점 (2026-10-22 정리 시점)

사용자 결정: "일단 여기까지 정리하고, 나중에 완성하고 디벨롭한다." 새 기능은 멈췄다. 이 절만 읽어도 이어서 시작할 수 있게 썼다.

### 현재 상태

- 제출 브랜치: `origin/main` = `origin/work/codex-runtime`(마지막 서비스 코드 `e270814`, 이후는 문서 커밋). 프론트는 `origin/work/claude-office`(소유: 프론트 세션)를 병합했다.
- 테스트: 백엔드 380건 OK(마지막 전체 실행 시점), 프론트 vitest 421건 OK, 총 커버리지는 89%(`e270814` 이전 측정). 부하가 높으면 10초 lease 때문에 일부 테스트가 간헐 실패한다(단독 재실행은 통과).
- **실서버 도달 단계**: 실제 `qwen3.5:4b`·Docker·API·worker·사무실로 live run 9개를 돌렸다(`docs/reports/live-runs-20261022.md`). 가장 멀리 간 것은 `fa83e2`: 기획 → 대안 → 작업 분해 → AC별 점검 → **기획 승인(사용자 클릭) → 빌더 진입**까지다. 빌더의 첫 `write_file` 3회가 모두 쓰기 범위 밖으로 거절돼(`write_scope`가 `/docker-compose.yml` 같은 절대경로였음) 진전 없음 `needs_input`이 됐다. 이 결함은 `e270814`로 고쳤고 그 뒤 새 run은 실행하지 않았다. 검증·보안·프리뷰·사람 확인은 실모델로 한 번도 실행하지 못했다.
- 실서버 프로세스는 사용자의 발표·시연을 위해 켜 둔 채다(Ollama, 메모리 감시자, API, worker). 사용자가 종료를 지시하면 내린다. 다시 띄울 때는 README "실행 방법"의 환경 변수와 순서를 따르되 시작 조건(여유 40% 이상, 스왑 2GB 미만)과 감시자를 쓴다. 재시작 때 이전 worker의 10초 lease가 남아 있으면 새 worker가 시작에 실패하므로 10초 이상 기다린 뒤 띄운다. 이전 API가 열린 연결 때문에 TERM으로 안 내려가면 그 pid만 강제 종료한다.
- 서비스 코드(`runner/worker.py` 등)를 바꾸면 `plan_inputs` 해시가 바뀌어 이미 만든 기획 승인이 낡은 것으로 보인다. 새 run으로 받는다.

### 이번 세션에서 실서버가 드러낸 서비스 결함과 수정(순서)

work_plan 영역 판정 누락 → 구조화 응답 강제(`7af3434`), 모델 원문 응답 보관 `model_outputs`(`7af3434`), Ollama 문법 400(역슬래시 패턴, `5244633`), 정정 조각 오류 피드백(`a7dc5af`), 점검 오류에 모델의 실제 id(`876be45`), 주기 2 반복 감지(`33fe0e7`), 점검 정책을 샘플링 스키마로 강제(`dd7d496`), 쓰기 범위 상대 경로(`e270814`). 공통 교훈: 4B가 반복해서 어기는 형식·정책은 사유 문구로 설득하기보다 **응답 스키마로 강제**하고 서버는 원 계약 스키마로 다시 검증한다.

### 후속 과제 (우선순위 순)

1. **상대 write_scope 적용 후 빌더 run**: 같은 범용 요청("할 일을 추가하고 완료 표시할 수 있는 간단한 웹 앱을 만들어 줘")으로 새 run을 돌려 빌더가 파일을 쓰는지, RED→GREEN 게이트가 4B에서 동작하는지 본다. 실모델이 `/work` 읽기 전용 마운트와 `/tmp`에 적응하는지도 처음 확인된다.
2. **4B의 GREEN**: 실행된 테스트 수≥1 규칙(`count_tests`)과 python 이미지에 pytest가 없다는 제약(unittest만) 아래에서 4B가 RED→GREEN을 끝내는지. 못 하면 막힌 단계를 그대로 기록한다.
3. **모델 친화적 피드백 보강**: 어느 항목이 왜 틀렸는지, 올바른 형식의 중립 예시. 필요하면 다른 반복 오류도 스키마로 강제한다.
4. **배포 대상(S10)**: 워커가 만드는 기획의 `repository`/`deployment`가 항상 null이라 `ReleaseOperations.prepare`는 실서버 run에서 만들어지지 않는다. 저장소·환경 선택은 사용자·운영자 결정이다.
5. **리뷰 잔여**(`docs/reports/code-review-f0-f6.md`): 재검토 N-5(`infra/verify_isolation.py`가 읽기 전용 `/work`를 기대하지 않음), N-6(접두사 재충돌, 거부는 됨), N-7(요약이 64KB 출력 상한에 잘리면 개수를 못 읽음), 그리고 첫 리뷰의 MEDIUM 잔여(grant 900초 만료 표시, 앱 미기동이 http 점검이 없으면 판정에 안 반영됨, 비UTF-8 파일이 보안 스캐너를 죽임, 재시도 task의 거짓 개입 표시·첫 task 사각지대, 예외 진단 로그, `/data` 볼륨 쓰기 권한) 및 LOW 8건.
6. **lease 간헐 테스트**: 부하 높을 때 10초 lease 때문에 실패하는 테스트(워커 heartbeat 의존)를 안정화한다.
7. **C7·C10**: AC 추적표 증거 연결, 관제·사용자 확인. **카공지도**는 설계안 C1–C10 완료 뒤에만 시험 입력으로 쓴다.
8. **사용자 결정 대기 항목**: 내려받은 7B 모델 2개(`qwen2.5-coder:7b`, `deepseek-coder:6.7b`)와 옛 Docker 볼륨 `lifecycle-*-data` 11개의 처분. 지우지 않았다.
9. **정리**: 원본 작업 트리(`/Users/seohyeokin/workspace/skala-AIMiniProject`, 로컬 main)에 커밋 안 된 변경이 많아 `origin/main`을 pull하면 충돌할 수 있다. 그쪽 소유 세션이 정리한다.

### 지켜야 할 규칙(요약)

서비스는 앱 코드·점검 내용·답을 대신 채우지 않는다. 사용자 결정(기획·배포·사람 확인 승인, 모델 교체, 통합 merge)을 합성하지 않는다. 실서버 실행 중에는 코드를 고치지 않고 서비스 결함이 드러나면 해당 run 평가를 종료·보존한 뒤 수정 커밋으로 새 run을 시작한다. 메모리 시작 조건과 감시자를 쓴다. 서브 에이전트를 띄우기 전에 사용자(또는 관제탑이 전한 사용자 결정)로 목적·모델·강도를 확인한다.
