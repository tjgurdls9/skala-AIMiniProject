# 런타임 세션 인계 (F5까지 완료, F4d 서버와 F6은 새 세션)

작성 시점의 런타임 worktree `.worktrees/codex-runtime`, 브랜치 `work/codex-runtime`. 이 문서 하나로 이어받을 수 있게 썼다. 관제탑 세션 이름은 `skala-aiminiproject-a7`(보고는 SendMessage로 이 이름에 보낸다).

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
