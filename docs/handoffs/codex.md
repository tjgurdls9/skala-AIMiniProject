# Codex CLI 인계 — 공통 준비·백엔드·런타임

## 현재 상태 — 2026-10-20

`READY_FOR_PARALLEL_IMPLEMENTATION` — Git 연결·두 브랜치/worktree·초안 보존을 실제 완료했다. Claude는 자기 worktree에서 예시 기반 F0–F5/F7을 시작할 수 있다. LIVE 연결은 아래 D1 제공자 계약을 명시 반영한 뒤 수행한다. 소비자 통합 확인은 아직 남았다. 제품 구현 완료·검토 PASS·배포 완료 신호가 아니다.

| 항목 | 확인 결과 |
|---|---|
| 원격 | `https://github.com/tjgurdls9/skala-AIMiniProject.git` · private · default `main` |
| 공통 기준 커밋 | `6cc9a0bd8c0e382f4a53a5e4a5fa32c7f5e04b18` (원격 실제 fetch 결과, 과거 `807ce7c`의 후속) |
| 원본 | `/Users/seohyeokin/workspace/skala-AIMiniProject` · `main` → `origin/main` 추적 |
| Codex | `/Users/seohyeokin/workspace/skala-AIMiniProject/.worktrees/codex-runtime` · `work/codex-runtime` |
| Claude | `/Users/seohyeokin/workspace/skala-AIMiniProject/.worktrees/claude-office` · `work/claude-office` |
| 초안 보존 커밋 | `049ed58` · Codex 브랜치만 · backend 6개/runner 2개 · 미검증 상태를 명시 |
| protocol v1 SHA256 | `ad6decc2849e1eb80af54b557c7cc61ee05e7ac2b70e92abdddeedd3990bb07d` |
| 공통 기준 HTTP 초안 SHA256 | `3e16e55ec6ff629013ceb41afa1ab94ba4378b36f583f4ab0bfd8a11d9827a1d` |
| D1 제공자 HTTP SHA256 | `9a10711627ee332f39e933caec4e1244de7bf679a0e88ce48b48c94e3d41f945` · CR-C01–C08 응답에 따른 추가 타입 |
| 포트 | 프론트 `127.0.0.1:5173`, API `127.0.0.1:8000`; 확인 당시 listener 없음. Vite의 `/api` 프록시 대상 `http://127.0.0.1:8000` |

### 수행·보존 근거

- 승인된 `.git` 쓰기와 네트워크로 `init`, origin 등록, fetch, main ref/index 연결, 두 worktree 생성을 수행했다. 원본 파일을 checkout으로 덮지 않았다.
- 원격 26개 추적 파일을 바이트 단위 비교해 전부 동일함을 확인했다. HTTP 초안은 이미 원격에 있다. backend/runner 8개는 로컬에만 있었다.
- 초안 8개를 Codex worktree로 복사한 뒤 원본/사본 바이트와 SHA256을 대조했다. 원본 초안은 삭제·변경하지 않고 원본에 untracked로 남겼다. 이후 제품 코딩은 Codex worktree에서만 한다.
- GitHub keyring 인증 정상, private 확인. 등록된 Actions workflow는 0개다. push·force push·배포는 하지 않았다. 외부 GitHub App/webhook 배포 연계는 미확인이다.
- 원본의 이 인계는 대기 중인 세션이 발견할 준비 신호 사본이다. 최신 구현 인계는 Codex worktree/브랜치의 같은 경로에서 읽는다. 다른 worktree에 문서·코드가 자동 반영되지 않는다.

### 작업 목록 (상태의 단일 원본)

| 작업 | 현재 상태·다음 결과 |
|---|---|
| D0 Git/worktree | 완료. 모델·Docker·배포 대상의 준비는 별도 미확인 |
| D1 계약/저장 | 제공자 계약·기본 저장/명령 연결. Claude 타입/fixture/API 상호 확인과 전체 도메인 완성은 남음 |
| D2–D3 | 기획 worker/lease/버전 fence/시도·문맥·중지/재개 구현, fake 기반 자체 검사. 실제 모델·긴 문맥 분해·역할 그래프 미확인/미연결 |
| D4–D6, D8–D11 | 미완료. 검색/MCP·격리 구현·두 검토·통합/실제 완주 증거 필요 |
| D7 | Claude 소유. 준비 완료 신호를 읽고 해당 worktree에서 시작 |

### Claude에게 필요한 요청

- **CODEX-BOOTSTRAP-001** 해결: 위 기준/브랜치/경로를 사용한다. 원본에서 코딩하거나 branch를 바꾸지 않는다.
- **CODEX-CONTRACT-001**: protocol v1은 위 기준 그대로 사용 가능. HTTP는 초안이므로 F6 LIVE 전송은 D1 응답/커밋 반영 후 연결한다. CR-C01–C08은 읽었으며 아래 구현 기록에서 같은 ID로 답한다.
- 추가 agent·agy를 기동하지 않았다. 기존 Claude 세션으로의 자동 전달·재개는 확인하지 않았으며, 이 파일을 준비 신호로 제공한다.

### 확인 범위·위험

Git/worktree·바이트/해시·포트·원격 메타데이터만 확인했다. 제품 테스트·API·모델 호출·Docker·배포는 아직 미실행이다. 원본의 보존 초안을 다시 stage하지 말고 Codex 브랜치의 보존 커밋을 사용한다. 독립 검증·보안 PASS를 주장하지 않는다.

## D1 계약 응답 — Claude 소비자에게

공유 계약은 protocol v1을 유지하고 HTTP v1에 타입을 추가했다. HTTP 초안의 ProjectCreate/CommandReceipt/Runtime 필드는 유지했다. 아래 응답은 제공자 연결 기준이며 소비자 타입/fixture 반영 완료를 뜻하지 않는다. 계약 커밋은 `2403a0ef979f44c7882ab74d965c713cffb6e546`이다. protocol 변경 없이 HTTP 타입/전송 의미와 이 응답만 분리했다.

| 요청 ID | 결정·실제 제공 형태·소비자 영향 |
|---|---|
| CR-C01 | 채택: loopback·허용 Origin + HttpOnly/SameSite=Strict 쿠키. POST/GET/DELETE `/api/session`; 변경 요청 `X-CSRF-Token`. 브라우저 Bearer 금지, SSE는 쿠키. 외부 공개 인증은 미지원. 계약 §7 참조 |
| CR-C02 | 기능 채택, 제안 필드명은 초안 유지: `{title,request}` → Project, runs는 `{mode,source_run_id?}` → 전체 Snapshot. `/api/replays` → ReplayRecordings. request_text를 보내면 422 |
| CR-C03 | 세부 기존 Runtime 채택: model_status/runner_status/live_available/reasons 등. 범용 status item 배열로 변경하지 않음. 생성 앱/배포 미연결을 reasons와 deployment_enabled=false로 표시 |
| CR-C04 | 채택: 202 CommandReceipt의 기존 `command_id,run_id,status:accepted,accepted_at`. accepted:true는 채택하지 않음. 오류 Error, 409 버전 충돌에 current_state_version 추가 |
| CR-C05 | 채택: 최초 ?after=, 재접속 Last-Event-ID 우선. event:lifecycle + Event, 약15초 주석 heartbeat. 범위 밖 event:resync 후 닫기. 현재 이벤트 전부 보존. 잘못된 cursor는 422 |
| CR-C06 | (a) 채택: spec 아티팩트의 PlanView. AC 정의·스택·대상·정책·가정·변경 설명 제공. Snapshot 변경 없음. AC 이행 상태는 아직 없음; 정의만으로 met 표시 금지 |
| CR-C07 | 계약 추가/실행 보류: Preview·Environment 타입과 환경 조회 경계 명시. 실제 격리 프리뷰·배포 대상 미설정, 현재 환경조회404·preview 아티팩트 없음. 임의 URL/같은 hostname 다른 port를 프리뷰로 신뢰하지 않음 |
| CR-C08 | 채택: 현재 Sprint를 running/ready에서 도출·표시. 중지 접수 후 Snapshot 확인. worker 버전/lease fence 사용. 외부 operation 아직 없음; 결과불명 사건을 합성하지 않음 |

Claude 요청: 이 계약 커밋만 자기 브랜치에 명시 반영(cherry-pick)하고 frontend 안의 타입·예시를 재생성한다. 제공자 구현 커밋은 소비자 타입 생성에 필요하지 않다. `http.v1.schema.json`의 상대 protocol 참조를 해석하고 새 HTTP 타입도 생성할 것. `/api` proxy와 `http://127.0.0.1:5173`을 사용하며, 생성 결과·타입/예시 확인·누락은 Claude 인계에 같은 요청 ID로 남긴다. frontend 파일은 Codex가 만들거나 수정하지 않았다.

## 구현·확인 기록 — 2026-10-20 (D1, D2–D3 일부)

### 수행 내용·커밋·파일

- `049ed58`: 원본 8개 파일 보존. 최종 확인에서도 원본 8개와 이 커밋의 바이트가 모두 같았다.
- `f4d08de`: 실제 worktree 준비 완료 인계.
- `2403a0ef979f44c7882ab74d965c713cffb6e546`: 공유 계약 전용. Claude는 자기 브랜치에서 이 커밋을 명시 반영한 뒤 타입/fixture를 생성한다. 다른 세션에 자동 적용하지 않았다.
- `a70a7b1e367ddc83f5d8949c1124398d1147f741`: 로컬 세션 인증/CSRF, API 오류·생성·SSE·REPLAY 목록, 영속 기획 worker·lease·중지/재개·문맥/시도와 최소 자체 검사.
- 변경 파일: `.gitignore`, `backend/{README.md,__main__.py,api.py,config.py,contracts.py,store.py,requirements.lock,tests/test_runtime.py}`, `runner/{model.py,worker.py}`, 공유 `docs/planning/{contracts.md,http.v1.schema.json}`, 이 인계. `frontend/**`와 Claude 인계는 수정하지 않았다.
- 직접 의존성은 초안 핀 그대로, 전이 설치 핀은 `backend/requirements.lock`에 기록했다. Codex worktree의 `backend/.venv`만 설치했다. 루트 공용 lock을 만들지 않았다.
- 적용 지침: 설치된 Ponytail, ECC contract-first/product-capability/context-and-decisions/strategic-compact/FastAPI/MCP 지침을 읽었다. 기존 기획·도메인 용어를 재사용했고 별도 기획 체계/서브에이전트를 만들지 않았다. MCP 지침을 읽은 사실을 제품 MCP 구현 완료로 취급하지 않는다.

### 실행 확인·관련 기준

- `backend/.venv/bin/python -m unittest discover -s backend/tests -v`: **13개 통과**, Python 3.14.7/macOS arm64, 외부 키·실제 모델·Docker 없이 임시 DB와 fake 모델만 사용했다.
- 범위: 쿠키/CSRF/Origin/Host/로그아웃, 요청 크기·잘못된 스키마, 실행기 부재의 LIVE 차단, 기획/승인/plan digest, 명령 멱등·중복 본문 충돌·버전 충돌, 승인 없는 building 차단, 중복 AC ID 차단, 중지 후 늦은 결과 차단/진행 중 요청 취소, lease 이중 인수 차단/인계 복구, 원문·정정/불변 원장 보존, 문맥 예산 초과 시 원문 보존, 실제 원장 REPLAY의 불변·읽기 전용 의미, SSE 직렬화/범위 밖 resync를 확인했다.
- `pip check`: 의존성 충돌 없음. `git diff --check`: 통과. 원격 26개 파일 일치·보존 초안 8개 바이트·두 worktree/브랜치·계약 해시를 확인했다.
- R04/AC03, R05/AC05, R11–13/AC11–12, R14–16/AC13, R25/AC22 관련 일부 서버 경계의 자체 근거다. AC01 전체 완주·AC06 범위 분류·AC09/10 독립 검토·AC15 장비 실측·AC16 제출 완주를 통과 판정하지 않았다.

### 미실행·실패·남은 위험

- 승인된 읽기 전용 D0 확인: Ollama `127.0.0.1:11434/api/tags` 연결 실패(curl exit 7). Docker는 `~/.docker/run/docker.sock` 부재로 데몬 연결 실패했다. 모델 다운로드·기동·추론, 컨테이너 생성/실행은 하지 않았다.
- 실제 모델 태그/라이선스/자원·한국어/JSON 품질은 미확정. 실제 모델 없이 만들어진 테스트 결과를 실제 LIVE 실행/배포 기록으로 제출하지 않는다. 이번 테스트 DB는 임시 파일이며 제출용 REPLAY를 만들지 않았다.
- provider 오류 시 자원 대기/실패를 보존한다. 기획 승인 뒤 격리 구현기는 아직 없어서 waiting_resource다. RAG/MCP·역할 그래프·생성 앱·서로 격리된 검증/보안·프리뷰·Git operation/배포는 미연결이다. 실제 배포는 사용자 승인 후에만 수행한다.
- 4,000 UTF-8 바이트의 보수적 입력 예산을 넘으면 원문을 자르지 않고 needs_input에 둔다. 긴 문맥 자동 분해는 미구현이다. 모든 수정 요청은 범위 분류 검증 전까지 보수적으로 재기획/재승인한다. 무한 반복을 짧은 횟수 뒤 합격으로 만드는 로직은 없다.
- 개발 브라우저·실제 SSE 소켓 재연결·프론트 타입 생성/fixture·통합·공개 서버·다른 OS/Python 설치·의존성 취약점/전체 비밀 검사·독립 검증/보안은 미확인이다. 알려진 키 형식 차단은 종합 보안 검사를 대신하지 않는다.
- push·원격 branch 생성·main 병합·배포·force push를 하지 않았다. 외부 GitHub App/webhook 연계는 미확인이다.
- 원본 main에는 준비/진행 인계 사본만 의도적인 미커밋 변경으로 남기며 backend/runner 보존 초안은 untracked 상태다. 원본 HTTP 스키마는 공통 기준 초안 그대로다. **최신 D1 계약/제품 코드는 Codex worktree에만 있다.**

### Claude 재개 요청·다음 착수점

- **CODEX-SESSION-001**: 사용자가 기존 터미널 Claude 세션의 제목을 `사무실 프론트엔드 담당 R&R`로 지정했다. Claude 앱 탐색은 중단했다. 터미널을 직접 조작하려는 도구 요청은 `Computer Use is not allowed to use the app 'com.googlecode.iterm2' for safety reasons.`로 거절됐다. 우회 입력/추가 프로세스 기동을 하지 않았고 **기존 CLI에 메시지 전달/재개는 확인되지 않았다**.
- 기존 Claude CLI에 전달할 내용: `READY_FOR_PARALLEL_IMPLEMENTATION. 원본 docs/handoffs/codex.md는 최신 인계 사본이다. /Users/seohyeokin/workspace/skala-AIMiniProject/.worktrees/claude-office (work/claude-office, 공통 기준 6cc9a0b)에서만 작업하라. 계약 커밋 2403a0ef979f44c7882ab74d965c713cffb6e546을 반영하고 CR-C01–C08 응답에 따라 frontend 타입/fixture와 F0–F7을 이어가라. backend 완료를 기다리지 말고 예시 화면을 진행하라. frontend 밖 코드·추가 agent·배포를 실행하지 말라. 결과와 누락은 docs/handoffs/claude.md에 남겨라.`
- 다음 Codex 작업: Claude 소비자 응답 확인 → 실제 Ollama 태그/실행 환경 확인 → 긴 문맥 분해·역할별 문맥/ACL 검색/MCP → Docker 격리 도구·템플릿 및 두 검토 연결. 실제 대상/모델이 없다는 이유로 가짜 성공을 채우지 않는다.

---

## 이전 인계 원문 (아래 BOOTSTRAP_REQUIRED 등은 당시 기록)

# 관제탑 → Codex CLI: 공통 준비 인계

## 현재 상태

`BOOTSTRAP_REQUIRED` — GitHub 비공개 저장소는 생성했다. 관제탑 환경에서는 프로젝트 `.git` 쓰기가 금지되어 `git init -b main`이 `Operation not permitted`로 실패했다. 로컬 Git·worktree가 준비됐다고 간주하지 않는다.

- 원격: https://github.com/tjgurdls9/skala-AIMiniProject
- 기본 브랜치: `main`
- 공개 범위: Private
- 원본 폴더: `/Users/seohyeokin/workspace/skala-AIMiniProject`
- 로컬 Git: 관제탑의 초기화 시도 차단. Codex CLI에서 현재 상태를 다시 확인할 것.
- 예정 worktree: `.worktrees/codex-runtime`, `.worktrees/claude-office`
- 예정 브랜치: `work/codex-runtime`, `work/claude-office`
- 제품 Infra 담당: Codex CLI. agy 배정 없음.

이 파일의 존재는 Claude 착수 허가가 아니다. 아래 작업을 끝낸 뒤 실제 경로·기준 커밋을 기록하고 `READY_FOR_PARALLEL_IMPLEMENTATION`으로 갱신해야 한다.

## Codex CLI가 먼저 할 일

1. 기존 사용자 변경·로컬 Git·원격·GitHub 접근을 확인한다. 관제탑과 CLI의 권한이 같다고 가정하지 않는다. 너도 `.git` 쓰기가 막히면 정확한 실패를 보고하고 우회하지 않는다.
2. 원본 파일을 삭제/덮어쓰지 않고 위 원격 `main`을 기준으로 로컬 Git을 연결한다. 이미 다른 원격/이력이 있으면 무단 교체하지 않는다. 원격 초기 이력을 force push로 지우지 않는다. 로컬 파일과 원격 기획의 차이는 보존하고 명시적으로 정리한다.
3. `.gitignore`를 적용하고 필요한 새 제품 파일만 관리한다. 강의 PDF·베이스 코드·키·가중치·`.worktrees`를 업로드하지 않는다.
4. 공유 프로토콜·요구사항·현재 스키마가 원격에 존재하는 기준 커밋을 확정한다.
5. 해당 기준에서 두 브랜치와 별도 worktree를 만든다. 기존 같은 이름의 경로·브랜치가 있으면 상태부터 확인한다. 상대 세션의 worktree를 지우거나 재활용하지 않는다.
6. 아래 준비 완료 항목을 채운 뒤 Claude가 자기 worktree에서 화면 작업을 시작할 수 있게 인계한다. HTTP 계약의 남은 세부 사항은 D1에서 조율하며, 프론트의 예시 기반 화면 작업 전체를 백엔드 완료까지 대기시키지 않는다.

## 준비 완료 시 기록할 항목

- 상태: 아직 `BOOTSTRAP_REQUIRED`
- 원격 기획 기준 커밋: `807ce7c149052db8f49f3ec7eea4207aa75940bf` — 관제탑이 업로드 후 원격에서 확인. 로컬 Git 기준 커밋과 구분한다.
- 두 worktree의 실제 절대 경로: 미생성
- 두 브랜치의 실제 이름: 미생성
- 원격 기준의 계약 식별: protocol v1 SHA256 `ad6decc2849e1eb80af54b557c7cc61ee05e7ac2b70e92abdddeedd3990bb07d`. HTTP 초안 SHA256 `3e16e55ec6ff629013ceb41afa1ab94ba4378b36f583f4ab0bfd8a11d9827a1d`는 미확정이며 업로드를 계약 합의로 취급하지 않는다.
- 로컬 API/프론트 포트: 미정
- 보존한 사용자 변경과 남은 제약: 실제 초기화 과정에서 기록

## Claude에게 전달할 준비 완료 신호

`READY_FOR_PARALLEL_IMPLEMENTATION`과 기준 커밋·자기 worktree 경로가 이 인계에 기록된 뒤에만 시작한다. Claude의 담당은 frontend 전체이며 Codex는 frontend 파일을 직접 수정하지 않는다. 현재 대화는 관제·범위/계약 조율에 사용한다.

---

## Codex 구현 세션 기록 — 2026-10-20

### 세션 구분과 현재 상태

- 현재 이 파일을 기록한 세션은 **Codex 구현 작업 세션**이다. 관제탑은 사용자가 별도로 운영하는 ChatGPT 대화다. 위의 관제탑 인계 원문은 보존했다.
- 결과·요청은 이 파일에만 기록하고 사용자가 다른 세션에 전달한다. 자동 세션 전달·폴링·서브에이전트 기동은 하지 않았다.
- Codex 소유권은 backend·runner·MCP/RAG·Infra·공유 계약·최종 통합이다. `frontend/**`는 Claude 소유이며 수정하지 않았다. agy에는 구현을 배정하지 않았다.
- 상태는 여전히 `BOOTSTRAP_REQUIRED`다. `READY_FOR_PARALLEL_IMPLEMENTATION`을 발급하지 않았다.
- 사용자 대기 지시 직전의 로컬 구현 초안은 보존했다. 이번 협업 방식 정정 후에는 현황 확인과 이 인계 기록만 수행했다.

### 수행 내용·변경 파일

신규 제품 코드가 없는 상태에서 아래 로컬 초안을 작성했다. 모두 **미검증·미커밋**이며 기능 완료나 독립 검토 PASS를 뜻하지 않는다.

| 경로 | 현재 내용·한계 |
|---|---|
| `.gitignore` | 참고 예제·PDF·가중치·키·DB·실행 데이터·worktree 제외 초안. 관제탑의 후속 변경은 보존했으며 최종 diff 검토 전이다. |
| `docs/planning/http.v1.schema.json` | ProjectCreate/Project/RunCreate/CommandReceipt/Runtime/Error 초안. 기존 프로토콜을 상대 `$ref`로 참조한다. HTTP 경로·인증·SSE 의미를 포함한 전체 계약 확정은 남아 있다. |
| `backend/__init__.py`, `backend/requirements.txt` | 백엔드 패키지와 직접 의존성 버전 지정. 별도 환경 설치·전이 의존성 lock·호환성 검증 전이다. |
| `backend/contracts.py` | 번들 JSON Schema 검증·정규 JSON 해시·도메인 오류 초안. |
| `backend/config.py` | 운영자 토큰·DB·명시적 모델 설정. 비밀 값은 읽거나 인계에 출력하지 않았다. |
| `backend/store.py` | SQLite 프로젝트·원문·스냅샷·명령·이벤트·명세·아티팩트·작업 등의 저장 초안. 명령 중복/버전/승인 검사, 중지·재개·수정·기록 재생 처리 코드. 작업 lease와 실제 복구 실행기·독립 검토·외부 operation 처리는 미연결이다. |
| `backend/api.py` | 인증·프로젝트/실행 생성·스냅샷·명령·SSE·runtime·아티팩트 경로 초안. worker heartbeat와 로컬 모델 준비를 검사하도록 작성했으나 worker 자체가 아직 없다. |
| `runner/__init__.py`, `runner/model.py` | loopback Ollama·명시적 Qwen/DeepSeek 태그·구조화 출력·단일 추론 슬롯 초안. 실제 모델 호출·정확 태그/라이선스/자원 검증 전이다. |

`all_total_vue_student/**`, PDF와 참고 리소스는 수정하지 않았다. 관제탑이 추가/수정한 루트 README·기획 문서·기존 인계 내용도 되돌리지 않았다.

### Git·계약 기준

- 사용자 지정 원격: `https://github.com/tjgurdls9/skala-AIMiniProject`, 비공개 생성 사실은 사용자와 관제탑 인계에서 전달받았다.
- 이 세션의 `git init -b main`: `.git: Operation not permitted`로 실패했다. 경계를 우회하지 않았다.
- `git status --short`: 현재도 `not a git repository`다. 로컬 브랜치·worktree·커밋·원격 설정은 만들지 못했다.
- `gh auth status`: 이 세션에서 기존 계정 토큰이 invalid로 보고됐다. 로그인/키 변경을 자동 수행하지 않았다.
- `git ls-remote ... HEAD refs/heads/main`: `Could not resolve host: github.com`으로 실패했다. 원격 `main` 커밋과 자동 배포 트리거를 확인하지 못했다. push·merge·deploy는 수행하지 않았다.
- 따라서 **기준 커밋은 없음**. 아래 해시는 현 로컬 파일 식별용이며 승인된 원격 계약 커밋을 대체하지 않는다.

| 계약 | SHA256 |
|---|---|
| `protocol.v1.schema.json` — 기존 v1, 이 세션에서 변경 없음 | `ad6decc2849e1eb80af54b557c7cc61ee05e7ac2b70e92abdddeedd3990bb07d` |
| `http.v1.schema.json` — 신규 로컬 초안 | `3e16e55ec6ff629013ceb41afa1ab94ba4378b36f583f4ab0bfd8a11d9827a1d` |

HTTP 초안 추가 이유는 기존 Snapshot/Command/Event에 없던 생성 요청·접수 응답·환경 진단·오류 본문을 공통 정의하기 위해서다. 기존 v1의 필드·열거 값은 바꾸지 않았다. 소비자 영향은 새 HTTP 타입 생성과 인증/SSE 어댑터 연결이며, Claude의 프론트 파일을 대신 생성하거나 수정하지 않았다. 확정 계약/기준 커밋 전달 전에는 이 초안을 실서버의 완료된 규격으로 취급하지 않는다.

### 확인한 사실과 미확인 사항

- 파일 목록·기획·협업 프로토콜·상대 인계 유무를 읽었다. 현재 `docs/handoffs/claude.md`는 없다.
- Python 3.11.15와 시스템의 FastAPI/jsonschema/httpx/LangGraph/uvicorn 설치 메타데이터를 확인했다. 실행/의존성 설치 성공 근거는 아니다.
- Docker CLI는 있으나 데몬 연결에 실패했다. 컨테이너 격리·이미지 생성·Compose 실행은 확인하지 못했다.
- Ollama CLI는 있으나 loopback HTTP 조회가 현재 샌드박스에서 `Operation not permitted`로 차단됐다. 서버 실행 여부나 설치 모델 유무를 확정하지 못했다.
- 테스트 작성/실행·API 기동·모델 추론·브라우저 확인·성능 측정은 하지 않았다. 현재 초안에는 아직 자체 검사가 없으므로 실행 가능한 완료 묶음으로 보고하지 않는다.
- 생성 앱 파일 수정·후보 커밋/이미지·독립 검증/보안·프리뷰·Git/배포·실제 기록 REPLAY 완주는 미구현/미실행이다. DB 테이블과 함수 이름만으로 이 기능들의 완료를 주장하지 않는다.
- 관련 기준: D0 준비 제약 확인, D1 저장/계약 초안, D2/D3 일부 코드 작성. AC03/05/11/13/22 관련 경계를 작성했지만 **어느 AC도 실행 통과로 판정하지 않았다**.

### 관제탑·다른 담당에게 전달할 요청

1. **CODEX-BOOTSTRAP-001**: 현재 세션도 `.git` 쓰기·GitHub 인증/DNS 제약이 있다. 쓰기와 원격 접근이 가능한 Codex CLI에서 관제탑의 원격 기준 커밋을 확인하고, 이 로컬 변경을 보존한 뒤 Git 연결·작업 브랜치·두 worktree를 준비해야 한다. 허용되지 않은 경로로 Git 메타데이터를 옮겨 우회하지 않는다. 준비가 끝나면 실제 기준 커밋·경로·브랜치와 함께 이 파일에 기록할 것.
2. **CODEX-CONTRACT-001 / Claude 전달용**: 기존 v1 프로토콜은 유지했다. HTTP 생성/runtime/접수/오류 초안은 위 경로에 있지만 확정 계약 커밋이 없다. 공통 준비 전에는 UI 착수 허가로 해석하지 않는다. 준비 후 Claude는 기존 프로토콜의 합성 예시 UI를 진행하고, 필요한 필드/동작은 `docs/handoffs/claude.md`에 요청 ID로 남겨주면 Codex가 같은 ID로 답한다.
3. 실제 배포는 사용자 승인 후에만 수행한다. 모델 다운로드·무료 외부 API 활성화·새 호스트 생성도 이번 기록에서 실행하지 않았다.

### 다음 착수점

사용자의 대기 해제와 공통 준비 상태를 받은 뒤, 현재 초안을 최소 self-check로 먼저 확인한다. HTTP 경로·오류·인증·cursor를 기계 계약과 문서로 확정하고 SQLite 트랜잭션/승인/중복/재생의 누락을 고친다. 이어서 영속 worker·버전 fence·중지/복구·필수 문맥 패킷·역할 ACL 검색/MCP를 연결한다. 그 다음 격리 구현/두 검토/Infra를 진행하며 전체 완주와 출시 완료는 별도 근거로 판단한다.

---

## 관제탑의 원격 업로드 완료 인계 — 2026-10-20

- 사용자 요청으로 사용량 한도에서 중단됐던 원격 기획·프로토콜 업로드를 재개했다.
- 비공개 저장소 `https://github.com/tjgurdls9/skala-AIMiniProject`의 `main`에 기획 기준 커밋 `807ce7c149052db8f49f3ec7eea4207aa75940bf`를 반영했다. 초기 커밋 `ae760480dad86e9283fee6cf1147f75ac512d2fa`를 부모로 보존했고 force push를 하지 않았다.
- 이 기준의 tree는 `bfa0045827258fbb08e72a8c99def90be91e3a67`이다. README·제외 정책·기획·계약/HTTP 초안·두 구현 프롬프트·각 담당 인계·합성 시험 기록 등 명시적으로 선택한 26개 파일을 올렸고 원격 목록과 내용을 식별하는 blob SHA를 확인했다.
- 강의 PDF·베이스 예제·키·모델 가중치·DB·제품 구현 초안(`backend/**`, `runner/**`)은 이 업로드에 포함하지 않았다. agy 시험은 `experiments/` 아래 자료이며 실제 CI/배포 워크플로로 활성화하지 않았다.
- 이 기록은 원격 기획 준비 완료다. 로컬 Git·두 worktree는 여전히 준비되지 않았으며 상태는 `BOOTSTRAP_REQUIRED`다. 위 Codex 구현 세션의 제약·미검증 내용과 Claude의 `WAITING_FOR_WORKSPACE`를 해소한 것으로 해석하지 않는다.
- **다음 담당은 Codex CLI**다. 허용된 환경에서 이 원격 기준과 로컬 미커밋 변경을 대조·보존하고 Git 연결·두 브랜치/worktree를 준비한다. 같은 권한 차단이 지속되면 우회하지 말고 실패를 보고한다. 실제 준비 뒤 기준 커밋·경로·브랜치를 기록하고 `READY_FOR_PARALLEL_IMPLEMENTATION`을 발급한다.
- Claude는 그 준비 신호를 받은 뒤 자기 worktree에서 시작한다. 관제탑이 두 구현 세션을 자동 재개하거나 메시지를 전송하지 않았다. 테스트·모델 호출·배포도 이번 업로드에서 수행하지 않았다.
