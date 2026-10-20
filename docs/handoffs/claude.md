# Claude CLI 인계 — 사무실 프론트엔드

담당: `frontend/**`, 프론트 의존성·lock, `frontend/src/generated/**`(계약에서 생성), `frontend/src/examples/**`, `frontend/README.md`, 이 파일. 백엔드·runner·Infra·공유 계약·루트 파일은 수정하지 않는다. 추가 에이전트는 기동하지 않았다.

## 현재 상태 — 2026-10-20

`WAITING_FOR_WORKSPACE` — 코드 착수 전.

- `docs/handoffs/codex.md` 상태가 `BOOTSTRAP_REQUIRED`다. 원본은 Git 저장소가 아니며 `.worktrees/claude-office`도 없다.
- 협업 §7-3과 Codex 인계에 따라, 원본에서 코딩하거나 `git init/switch`를 하지 않았다. `frontend/` 디렉터리도 만들지 않았다.
- 이 세션의 산출물은 이 파일 하나다. 기준 커밋: 없음.
- `READY_FOR_PARALLEL_IMPLEMENTATION`, 기준 커밋, claude-office worktree 절대 경로가 Codex 인계에 기록되면 그 worktree에서만 착수한다.

## 읽은 입력

- `DEVELOPMENT_AGENT_DESIGN.md`, `docs/planning/{requirements,experience,contracts,collaboration}.md`, `acceptance.md`(AC03–07, AC16–19, §3 실패 시나리오), `docs/prompts/CLAUDE_IMPLEMENTATION.md`, `docs/handoffs/codex.md`
- 계약 스키마 `docs/planning/protocol.v1.schema.json`
  - SHA256 `ad6decc2849e1eb80af54b557c7cc61ee05e7ac2b70e92abdddeedd3990bb07d` (10472 bytes, 원본 폴더 기준, 커밋 미확정)
- 원본의 `backend/api.py`는 커밋·인계 전 진행 중인 코드다. 계약 요청 중복을 피하려고 경로·오류 형태만 읽기 전용으로 확인했다. 이를 확정 계약으로 소비하지 않는다.

## 착수 시 구현 계획 (worktree 준비 후)

구성: Vue 3 + Vite + TypeScript. 상태 프레임워크·3D 엔진·외부 폰트는 쓰지 않는다. 소비자 타입은 `json-schema-to-typescript`(버전 고정, devDependency)로 스키마에서 `src/generated/protocol.ts`를 생성한다.

| 묶음 | 내용 | 관련 AC |
|---|---|---|
| F0 | 프로젝트 골격, 타입 생성 스크립트, 출처 어댑터 경계(`example` / `live` / `replay`) — UI는 같은 Snapshot을 소비 | — |
| F1 | 합성 예시 Snapshot·Event 세트: 빈 상태, 기획 승인 대기, 구현 중, 검증 통과·보안 실패, 프리뷰, 배포 승인 대기, 무료 소진·자원 대기, 실패, 중지. 화면 고정 배지 “합성 예시 · 실제 실행 아님”. 예시 조작은 로컬 상태만 바꾸고 외부 효과 없음 | AC16 |
| F2 | 상단 바(출처 배지 LIVE/실제 REPLAY/합성, 상태, 명세 버전, 항상 보이는 중지), 프로젝트→Phase→Sprint→작업→아티팩트 트리, Sprint 집계 지도, 작업 수 진행과 AC를 분리 표시 | AC07 |
| F3 | 사무실 Canvas(회의실→구현 구역→분리된 검증실·보안실→출시 게이트). 선택 Sprint만 표시, 수신한 사건만 연출, 숨김·모션 감소 시 정적 렌더. 동등한 DOM 목록 | AC17 |
| F4 | 근거 패널(작업·AC·아티팩트·두 보고서 별도), 시간순 사건 기록, 실패·보안 차단·무료 소진·승인 대기 고정 영역 | AC07, AC10 |
| F5 | 기획 승인 dialog, 프리뷰(제한 iframe, 별도 origin)·수정 요청(구현/기획 구분, 입력 초안 보존), 배포 승인 dialog(서버 대상 그대로 전송). 202는 “접수”로만 표시, 409 시 피드백 보존과 최신 대상 재조회 | AC03–06 |
| F6 | live 어댑터: Snapshot GET, SSE seq 중복 제거·누락 시 재동기화, heartbeat는 진행으로 취급하지 않음, 연결 끊김과 실행 실패 구분. LIVE 오류 시 예시로 자동 전환하지 않음 | AC16 |
| F7 | 로컬 관련도 보조(work_kind·depends_on 기반 강조, “로컬 관련도 보조” 표기), 1440/1024/390px, light/dark와 office 테마 분리, 키보드·포커스·대비 | AC17–19 |

F0–F5와 F7은 계약 확정 전에도 예시로 진행할 수 있다. F6과 F5의 실제 전송은 아래 계약 요청이 답변된 뒤 연결한다.

## 계약 변경·확정 요청

형식: 요청 ID / 사용자 동작 / 현재 계약의 부족 / 제안 / 호환성 영향 / 그동안 가능한 UI 작업.

**CR-C01 브라우저 인증 방식**
- 동작: 사무실 화면이 API·SSE를 호출한다.
- 부족: 진행 중인 `backend/api.py`는 `Authorization: Bearer <token>`을 검사한다. 프론트 지침은 “브라우저에 secret 금지”다. 또한 `EventSource`는 사용자 헤더를 보낼 수 없다.
- 제안: 로컬 모드에서는 같은 origin과 loopback 바인딩, 서버가 발급하는 HttpOnly·SameSite=Strict 세션 쿠키를 쓰고, 상태 변경 요청에 CSRF 방어를 둔다. 토큰을 프론트 번들·URL·localStorage에 넣지 않는다.
- 영향: 서버 인증 계층. 스키마 필드 변경은 없다.
- 가능한 작업: 인증을 제외한 전체 화면.

**CR-C02 프로젝트·실행 생성 요청·응답 스키마**
- 동작: 최초 요청 입력 → 프로젝트 생성 → LIVE 실행 생성. 또는 실제 기록을 REPLAY로 선택한다.
- 부족: `POST /api/projects`, `POST /api/projects/{id}/runs`의 본문·응답 스키마와 재생 가능한 실제 기록 목록 조회 경로가 없다.
- 제안: projects 요청 `{title, request_text}` → `{project_id}`. runs 요청 `{mode: "live"}` 또는 `{mode: "replay", source_run_id}` → `{run_id}` 후 Snapshot GET. 재생 목록 `GET /api/replays` → `ReplaySource[]`.
- 영향: 추가만 있음.
- 가능한 작업: 입력 폼과 출처 선택 UI.

**CR-C03 `GET /api/runtime` 응답 스키마**
- 동작: 실행 가능성(로컬 모델, 실행기, 무료 자격, Git·배포 대상)을 표시한다.
- 부족: 응답 필드가 미정이다.
- 제안: 항목별 `{id, label, status: "ready"|"missing"|"unverified"|"exhausted"|"error", reason?}`. 키 존재 여부만으로는 `ready`가 되지 않는다.
- 영향: 추가만 있음.
- 가능한 작업: 상태 칩 UI(예시 데이터).

**CR-C04 명령 접수(202)와 오류 본문**
- 동작: 승인·수정·중지·재개 클릭 후 접수와 실패를 구분해 표시한다.
- 부족: 202 본문이 미정이다. 오류 본문 `{error:{code,message}}`가 계약 문서에 명시되지 않았다. 409 `STALE_APPROVAL`/`VERSION_CONFLICT`에서 최신 대상을 다시 읽을 단서도 없다.
- 제안: 202 `{command_id, accepted: true}`(새 상태는 이벤트와 Snapshot으로만 확인). 오류 `{error:{code,message,current_state_version?}}`를 스키마에 추가한다.
- 영향: 추가만 있음. 기존 오류 형태와 호환된다.
- 가능한 작업: 접수/충돌 UI, 피드백 초안 보존.

**CR-C05 SSE 연결 세부**
- 동작: 재접속, 누락 복구, 끊김 표시.
- 부족: 최초 cursor(진행 중인 코드의 `?after=` 쿼리와 `Last-Event-ID` 헤더 중 무엇을 쓰는지), heartbeat 형식, 이벤트 보존 구간이 사라졌을 때의 재동기화 신호가 미정이다.
- 제안: 최초 연결 `?after=<snapshot.last_event_seq>`, 재접속은 브라우저 `Last-Event-ID`. heartbeat는 SSE 주석 줄(`: ping`). 보존 구간 밖이면 `event: resync`를 보내고 클라이언트가 Snapshot을 다시 읽는다.
- 영향: 전송 계약 문서화만 필요하다.
- 가능한 작업: 예시 이벤트 재생으로 seq 중복 제거·누락 처리 로직을 먼저 구현한다.

**CR-C06 기획 승인 화면 표시 데이터**
- 동작: 목표·기능·비범위·AC·스택·저장소/브랜치·배포 대상·무료 정책·원문 대비 변경점을 한 화면에서 읽고 승인한다.
- 부족: Snapshot에는 `PlanTarget`(digest 3개)과 `Artifact.public_summary`만 있다. 명세 내용 형식, AC 정의(ID 외 제목·설명), AC 충족 상태가 없다.
- 제안: (a) `kind: "spec"` 아티팩트의 `GET /api/artifacts/{id}` 응답을 정해진 JSON 형식(PlanView)으로 제공하거나, (b) Snapshot에 `acceptance: [{id, title, status: "unmet"|"met"|"failed"|"not_run"}]`를 추가한다.
- 영향: (b)는 Snapshot 스키마 확장이고 `additionalProperties: false`라서 프로토콜 버전 검토가 필요하다.
- 가능한 작업: 승인 dialog 레이아웃. AC는 ID만 표시하고 충족 현황은 “계약 대기”로 표시한다.

**CR-C07 프리뷰 주소와 배포 환경 표시 정보**
- 동작: 프리뷰를 제한 iframe으로 열고, 배포 승인에서 환경 이름·노출 범위를 확인한다.
- 부족: `kind: "preview"` 아티팩트에서 미리보기 URL·origin을 얻는 방법이 없다. `environment_id`만으로는 표시 이름·공개 범위를 알 수 없다.
- 제안: preview 아티팩트 응답에 `{url, origin}`(서버가 허용한 별도 origin만). 환경 조회 `GET /api/environments/{id}` → `{id, label, exposure}`.
- 영향: 추가만 있음.
- 가능한 작업: 프리뷰·배포 dialog. 예시에서는 iframe 대신 “합성 예시 — 프리뷰 없음” 자리표시를 쓴다.

**CR-C08 “현재 Sprint”와 중지 처리 중 상태 (확인 요청)**
- 부족: Snapshot에 현재 Sprint 지정이 없고, RunState에 “중지 처리 중”(취소 접수 후 외부 작업 결과 대기)이 없다.
- 제안: 현재 Sprint는 프론트가 `running`/`ready` 작업에서 도출하고 “도출”이라고 표기한다. 중지 처리 중은 접수된 pause/cancel 명령과 `operation_uncertain` 이벤트로 표시한다. 서버 쪽 지정이 필요하면 Codex가 판단한다.
- 영향: 채택하면 변경 없음.

## 미확인·미실행

- 코드·빌드·브라우저·모바일·키보드·성능 확인: 모두 미실행이다. 코드가 아직 없다.
- 소비자 타입 생성: 미실행이다.
- 이 세션의 자기 점검은 독립 검증·보안 판정이 아니다.

## Codex에게 필요한 것

1. `READY_FOR_PARALLEL_IMPLEMENTATION`, 기준 커밋, `.worktrees/claude-office` 실제 경로, 계약 SHA256, 프론트 개발 포트(기본 제안 5173), API 프록시 대상 포트
2. 위 CR-C01–C08에 대한 같은 ID 답변(채택·보류·거절과 계약 커밋)
