# Claude CLI 인계 — 사무실 프론트엔드

담당: `frontend/**`(의존성·lock·생성 타입·예시 포함)와 이 파일. 백엔드·runner·Infra·공유 계약·루트 파일은 수정하지 않았다. 추가 에이전트는 기동하지 않았다.

## 최신 — P01–P03 프론트 보완, S08-DESIGN: 사용자 디자인 지시 대기 (2026-10-20)

이 절은 아래의 이전 기록보다 우선한다. 지시는 원본의 `docs/prompts/CLAUDE_PHASE_COMPLETION.md`와 `docs/planning/phase-completion.md`를 따른다. 기준은 Claude `b3a52bc`, Codex `c3e11c1`이다.

**현재 상태: `S08-DESIGN: 사용자 디자인 지시 대기`**
- P01–P03의 프론트 기능 연결을 커밋했다. P04/S08 본격 화면 개편은 이 세션 사용자의 직접 디자인 지시를 받은 뒤 시작한다.
- 이 대기는 개발용 인계이며, 제품 API의 기획·배포 승인 사건이 아니다. 기다린 시간이나 무응답은 지시나 동의가 아니다.

### 계약 기준

- Codex 쪽에 계약 전용 커밋이 없었다. 계약 변경이 구현 커밋 `44d8670`, `8648fca`, `c3e11c1`에 섞여 있었다. 그래서 `docs/planning/{http.v1.schema.json,contracts.md}` 두 경로만 `c3e11c1` 상태로 바이트 그대로 가져와 `dc1407c`로 커밋했다. protocol은 변경이 없다.
- protocol v1 `ad6decc2849e1eb80af54b557c7cc61ee05e7ac2b70e92abdddeedd3990bb07d`, http v1 `a7f384026fbde0f6dfe0c29f853c42911b000fefa0a95ee792424fb5dc909b4f`. Codex 인계의 해시와 일치한다.
- 소비자 타입은 기존 고정 도구(`npm run gen:types`)로 재생성했다. `AcceptanceStatus`가 추가됐다.

### Sprint별 결과

| 개발 Sprint | 커밋 | 프론트 반영 | 남은 것 |
|---|---|---|---|
| S02 (P01) | `1140e00` | CR-C09: `/api/runs/{id}/acceptance`를 소비한다. AC별 `met/unmet/failed/not_run`과 근거 검증 보고서를 Sprint·작업에 표시하고, 작업 수와 보안 실패와는 따로 둔다. 늦은 응답은 버리고, 명세가 다른 판정은 숨기고 불일치를 알리며, 읽기 오류를 표시한다. 재생은 "기록 당시 동결"로 표기한다. CR-C10: preview 본문을 `http.Preview`로 읽는다. CR-C11: 같은 `command_id` 사건이 POST 응답보다 먼저 와도 확인이 끝나고 늦은 202가 다시 대기를 만들지 않는다(테스트). CODEX-UI-001: iframe은 LIVE이면서 `preview_ready`이고 현재 후보 커밋일 때만 마운트한다. 재생·옛 후보·다른 단계·예시는 기록 주소·커밋만 텍스트로 보여준다 | 실제 LIVE 화면의 AC 판정 갱신 흐름 |
| S03–S05 (P02) | `8f7cd8d` | L2: 누락 재동기화를 0초, 0.5초, …, 최대 30초로 늘리며 횟수 상한은 두지 않는다. 수동 재연결은 대기를 취소하고, 형식 오류 사건은 알린다. L3: 사건을 제자리에 쌓고 100ms 묶음으로 화면에 게시한다(1만 건 테스트). 재개 버튼은 서버가 받는 상태(`store.py` 기준 paused·waiting_*·needs_input·failed)에서만 보이고 최종 판정은 서버가 한다. needs_input·failed에서는 서버 이유와 함께 `request_changes`(spec)로 재기획을 요청한다. 근거 패널에 공개 검색·문맥 근거를 표시하고, 없으면 없다고 명시한다 | 검색 근거 본문 형식(CR-C12). 서버가 아직 retrieval 아티팩트를 발급하지 않는다 |
| S06–S07 (P03) | `7b865b7` | 후보(명세·커밋·이미지)별 검토 회차를 현재와 과거로 나눈다. 두 판정은 각자 보여주고, 한쪽 통과를 통과로 표시하지 않으며, 과거 원본도 열 수 있다. 두 보고서의 대상이 다르면 경고한다 | — |
| 가독성 | `ccbd023` | 실제 32자 ID가 헤더를 무너뜨려 앞 8자만 보이게 하고 전체는 title로 둔다. 사건 시각을 `HH:MM:SS`로 바꿨다 | — |

### 실행한 확인

- `npm test`: 11개 파일, 161개 통과. coverage(P03 시점): 구문 91.6%, 분기 87.1%, 함수 85.8%, 라인 94.1%. `vue-tsc` 오류 0. `vite build`: JS gzip 59.2KB.
- 실제 기록 확인: `c3e11c1`을 `git archive`로 scratchpad에 내보냈다. Codex의 `runtime-data/development-check.sqlite3`는 `sqlite3 .backup`으로 사본만 만들어 그 사본으로 서버를 실행했다. 원본 DB와 Codex worktree에는 쓰지 않았다.
- 그 사본에서 실제 원장 3건("[개발 자체확인·합성]", 스크립트 승인)을 재생했다. 1440px에서 실제 Phase·Sprint, 작업 6개, AC 6개 충족과 근거 검증 보고서, 두 검토 PASS의 같은 대상, 취소 상태, 읽기 전용을 확인했다.
- 실제 LIVE 실행(worker·모델 기동), 실제 사용자 승인, 장시간 재연결은 실행하지 않았다.

### Codex에게 요청

- **CR-C12 검색 근거 본문 형식**: `kind: retrieval`(또는 context) 아티팩트 본문을 기계 계약으로 정해 달라. 출처, 문서 버전, 라이선스, 수집 시점, 본문 해시, 역할 ACL, 결과 없음과 검색 실패의 구분이 필요하다. 현재 서버는 retrieval 아티팩트를 발급하지 않아 프론트는 "공개 근거 없음"만 표시한다.
- **CR-C13 재생 `recorded_at`**: `GET /api/replays`의 `recorded_at`이 조회할 때마다 현재 시각으로 바뀐다(22:32:53, 22:33:12에 같은 기록 확인). 재생 실행의 `replay_source.recorded_at`도 재생 생성 시각이다. 원본 기록 시점이 들어가야 하는지 확인해 달라. 프론트는 서버 값을 그대로 표시한다.
- 통합: `work/claude-office`의 `dc1407c`…`ccbd023`. 계약 채택 커밋 `dc1407c`는 Codex의 두 파일과 바이트가 같다.

### P04 직전: 현재 화면과 남은 S08 범위

- 화면 구조(기능 기준, 디자인은 첫 구현 그대로):
  - 시작 화면: 새 요청, 실행 가능성, 실제 기록 재생, 합성 예시
  - 작업 화면:
    - 헤더: 출처 배지, 상태, 연결, 중지·재개·취소
    - 고정 알림
    - 왼쪽: 작업 지도 트리
    - 가운데: Sprint 지도와 목표·AC, Canvas 사무실과 DOM 좌석 목록, 결정 버튼, 사건 기록
    - 오른쪽: 근거 패널(작업·아티팩트·AC·검색 근거·검토 쌍·회차)
  - dialog: 기획 승인, 프리뷰·수정, 배포 승인, 재기획 요청, 재개·취소
- 실제 데이터로 연결된 것: Snapshot, 사건, AC 판정, PlanView, Preview, 명령 접수와 반영, 재생, 오류.
- 미연결: 검색 근거 본문(CR-C12), 배포·환경·복구(D9 미구현), 실제 기록 export·import(S12).
- 사용자 지시 뒤 S08에서 다룰 범위: 레이아웃·사무실 표현·색감·정보 밀도·움직임, 실제 데이터에서 드러난 정보 위계(긴 ID·해시, AC 목록 길이, 검토 회차의 위치).

### 다음 행동

1. 이 세션의 사용자에게 직접 디자인 지시를 요청했다. 지시가 오면 원문과 변경점을 이 파일에 보존하고 S08을 구현한다.
2. 지시와 무관한 P05 프론트 작업(배포·복구 대상 표시, 키 없는 재생·import)은 Codex의 D9–D12 계약과 산출물이 필요하다. 현재 제공되지 않아 대기한다. 이미 있는 배포 승인 화면(서버 대상 그대로 전송, 202와 결과 구분)은 유지한다.

---

## 이전 기록 — 첫 구현·리뷰 (2026-10-20)

`FRONTEND_EXAMPLES_AND_LIVE_ADAPTER_READY`(당시 상태) — 아래 두 단계를 구분한다.

| 단계 | 상태 |
|---|---|
| 합성 예시 기반 화면(F0–F5, F7) | 구현했다. 브라우저에서 1440/1024/390px, 다크, 모션 감소를 확인했다 |
| 실제 API 연결(F6) | 어댑터를 구현했다. Codex `a70a7b1`의 scratchpad 사본 서버로 세션·runtime·replays·404를 확인했다. 모델·실행기가 없어 LIVE 실행 생성 → 기획 승인 → SSE 반영 흐름은 확인하지 못했다 |

제품 완료, 독립 검증·보안 PASS, 배포 완료를 뜻하지 않는다. 이 세션의 자기 점검은 독립 판정이 아니다.

## 기준·브랜치·계약

| 항목 | 값 |
|---|---|
| worktree | `/Users/seohyeokin/workspace/skala-AIMiniProject/.worktrees/claude-office` |
| 브랜치 | `work/claude-office` (push 안 함) |
| 공통 기준 | `6cc9a0bd8c0e382f4a53a5e4a5fa32c7f5e04b18` |
| 계약 반영 | `2403a0e`를 cherry-pick해 `f151930`으로 반영했다. 충돌은 `docs/handoffs/codex.md` 한 곳뿐이었다. Codex의 `2403a0e` 버전을 수정 없이 채택해 해소했다. 계약 두 파일은 변경 없이 반영했다 |
| protocol v1 SHA256 | `ad6decc2849e1eb80af54b557c7cc61ee05e7ac2b70e92abdddeedd3990bb07d` |
| http v1 SHA256 | `9a10711627ee332f39e933caec4e1244de7bf679a0e88ce48b48c94e3d41f945` (Codex 인계의 D1 해시와 일치) |
| 프론트 커밋 | `968bbe9` 기반 계층(타입·출처·예시·useRun) / `046f02c` 화면·테스트 / `c7f56a3` 인계 / `ef1dd16` 코드 리뷰 반영 / M3 정정 커밋(아래 절) |

## 변경 파일

모두 `frontend/` 아래에 있으며, 이 인계 파일만 예외다.

- 설정·도구: `package.json`, `package-lock.json`(정확 버전 고정: vue 3.5.44, vite 8.3.4, typescript 5.9.3, vue-tsc 3.3.13, vitest 5.0.5, json-schema-to-typescript 16.0.0, ajv 8.20.0 등), `vite.config.ts`, `tsconfig.json`, `index.html`, `scripts/gen-types.mjs`, `README.md`
- 생성: `src/generated/{protocol,http}.ts`와 각 `.sha256`
- 로직: `src/api/*`, `src/composables/*`, `src/model/*`, `src/office/*`, `src/examples/*`
- 화면: `src/components/*.vue` 21개, `src/App.vue`, `src/main.ts`, `src/styles/base.css`
- 테스트: `tests/*.test.ts` 7개

## CR-C01–C08 반영 결과

| 요청 ID | 프론트 반영 |
|---|---|
| CR-C01 | `LiveApi`는 GET/POST `/api/session`과 메모리 CSRF(`X-CSRF-Token`)를 쓰고, 401이면 한 번 재연결한다. Bearer·저장소·URL 토큰은 쓰지 않는다. 프론트 주소는 `127.0.0.1:5173`으로 고정했다(`strictPort`) |
| CR-C02 | `{title, request}` → Project, `{mode, source_run_id?}` → Snapshot(`run_id`), `/api/replays` |
| CR-C03 | `http.Runtime` 필드를 그대로 표시한다. `live_available=false`이면 시작 버튼을 막고 `reasons`를 보여준다 |
| CR-C04 | 202 `CommandReceipt`는 "접수됨 · 반영 확인 중"으로만 표시한다. `http.Error`, 409(`current_state_version`)이면 의견을 보존하고 스냅샷을 다시 읽는다 |
| CR-C05 | `?after=` 최초 연결, 브라우저 `Last-Event-ID` 재연결, `event: lifecycle` 파싱, `event: resync`면 닫고 스냅샷부터 다시 연결한다. heartbeat는 무시한다 |
| CR-C06 | spec 아티팩트를 `http.PlanView`로 읽는다. 승인 대상과 `spec_version_id`가 다르면 승인을 막는다. AC는 정의만 보여주며 충족 표시는 하지 않는다 |
| CR-C07 | `http.Preview`는 다른 hostname일 때만 sandbox iframe으로 연다. 환경 404는 "미설정"으로 표시한다 |
| CR-C08 | 현재 Sprint는 running → ready → 실패·차단 → 대기 순으로 도출하고 "도출"이라고 표기한다. 중지는 접수 뒤 스냅샷으로 확인한다 |

`npm run gen:types`로 두 스키마의 소비자 타입을 생성했다. 상대 `$ref`도 해석된다. 생성 결과에 필드를 수기로 추가하지 않았다.

## 실행·확인한 것

| 확인 | 결과 |
|---|---|
| `npm test` (Vitest 5.0.5, happy-dom) | 7개 파일, 120개 통과 (리뷰 회귀 테스트 포함) |
| `npm run coverage` | 구문 91.4%, 분기 86.4%, 함수 86.5%, 라인 93.9% (`src/generated` 제외) |
| 계약 적합성 | 합성 예시 9종의 Snapshot·Event, PlanView, Environment를 ajv 2020으로 실제 스키마에 대조했다. 사건 seq 연속성, ID 참조 존재, `replay_source` 없음도 확인했다 |
| `vue-tsc --noEmit` | 오류 0 |
| `vite build` | JS 159.6KB(gzip 54.9KB), CSS 16.2KB(gzip 4.2KB) |
| `npm audit` | 0건 |
| 브라우저 (Chrome DevTools MCP, 격리 컨텍스트) | 아래 별도 표 |

브라우저 확인 내용:

| 항목 | 결과 |
|---|---|
| 확인한 화면 | 1440: 시작·구현 중·기획 승인 / 1024: 배포 승인 / 390: 모바일·다크·모션 감소, 검증 통과·보안 실패 |
| 레이아웃·터치 | 390px 가로 넘침 없음(`scrollWidth = 390`). 32px 미만 조작 요소는 44px label 안의 체크박스 하나뿐이다 |
| dialog·키보드 | 기획 승인 dialog를 Esc로 닫으면 포커스가 여는 버튼으로 돌아간다. 예시 모드 승인은 "보내지 않음"으로 표시된다 |
| 실제 API | Codex `a70a7b1`을 `git archive`로 scratchpad에 내보낸 사본, `LIFECYCLE_DB`도 scratchpad, Codex venv Python으로 실행했다 |
| API 응답 | 세션 쿠키 연결, `/api/runtime`(LIVE 불가 이유 3개), `/api/replays`(빈 목록), 없는 실행의 404 표시를 확인했다. 서버는 확인 후 종료했다. Codex worktree에는 쓰지 않았다 |
| 스크린샷 | 확인용으로만 찍었고 저장소에 포함하지 않았다 |

## 코드 리뷰 반영

사용자 승인을 받아 코드 리뷰 서브에이전트 1개(ecc:code-reviewer, sonnet, high, 읽기 전용)를 실행했다. 이 리뷰는 개발 세션의 자체 점검이며, 제품의 독립 검증·보안 판정이 아니다.

판정은 조건부 승인이었다: CRITICAL 0건, HIGH 1건, MEDIUM 7건, LOW 7건.

| ID | 내용 | 조치 |
|---|---|---|
| H1 | "강조 항목만" 필터와 반복 묶음이 실패 종료·검토 제출·상태 변경 사건을 숨길 수 있었다 | 해당 유형은 필터와 묶음에서 제외해 항상 보이게 했다. 묶을 때 처음과 마지막 요약을 함께 보여준다. 숨긴 건수는 필터 기준으로 센다 |
| M1 | 재생에서도 기획·배포 승인 버튼이 활성이었다 | 두 dialog에 `readOnly`를 추가했다. `send`에서 재생이면 `REPLAY_READ_ONLY`로 바로 막는다 |
| M2 | 명령 ID가 다이얼로그·대상과 묶이지 않았다 | 새로 열거나 대상이 바뀌면 새 ID를 만든다. 409 원인 안내는 대상이 바뀌어도 남긴다. 같은 ID 재사용은 열린 화면 안의 네트워크 재시도뿐이다 |
| M3 | 접수된 명령의 확인 표시가 무관한 버전 변화로 풀리거나, 영원히 잠길 수 있었다 | 같은 `command_id`가 담긴 사건으로만 확인한다. 스냅샷 `state_version` 증가로는 풀지 않는다. 20초 안에 근거가 없으면 조작을 풀고 "반영 미확인"을 알린다. 아래 정정 참고 |
| M4 | 다시 연결이 세션 복구보다 SSE를 먼저 열었다 | 스냅샷(세션 재발급 포함)이 성공한 뒤에만 SSE를 연다 |
| M5 | 작은 버튼이 44px 미만이었다 | 터치 기기(`pointer: coarse`)에서 모든 버튼을 44px 이상으로 했다 |
| M6 | 승인 뒤 여는 버튼이 사라지면 포커스가 body로 떨어졌다 | 작업 공간 `main`(`tabindex=-1`)으로 돌린다 |
| M7 | PlanView를 검증 없이 캐스팅했다 | 필수 필드를 모두 확인하는 공용 가드를 추가했다. 형식이 틀리면 승인을 막는다 |
| L1 | resync 뒤 사건 목록이 커서와 맞지 않았다 | 새 커서 이후의 사건을 버린다. 스냅샷 실패 시 낡은 커서로 연결하지 않는다 |
| L4·L6 | 일시 중지 오류가 남았고, 새 결정 대기가 낭독되지 않았다 | 상태가 바뀌면 오류를 지운다. 새 결정 대기를 polite live region으로 한 번 알린다 |
| L5 | 프리뷰 조회 실패가 미연결 문구로 보였고, 늦은 응답이 끼어들 수 있었다 | 조회 오류는 따로 표시한다. 응답 ID를 확인하고, 로딩 상태도 같은 요청일 때만 끈다 |
| L7 | 실행 생성 재시도 때 프로젝트가 중복 생성됐고, 재생 버튼을 연속으로 누를 수 있었다 | 같은 입력이면 프로젝트를 재사용한다. 재생 버튼은 보내는 중에 막는다 |

### M3 정정 — 관제탑 지적 반영

- **무엇이 틀렸나**: `ef1dd16`에서 M3를 고쳤다고 보고했다. 그러나 `useRun.ts`의 `applySnapshot`에는 "스냅샷 `state_version`이 명령 시점보다 크면 확인 표시를 지운다"는 조건이 남아 있었다. 다른 작업으로 버전이 올라가도 내 명령이 반영된 것처럼 보였다. 테스트도 같은 명령 사건과 시간 초과만 다뤘다. 보고가 코드보다 앞서 나갔다.
- **확인한 서버 동작**: Codex `a70a7b1`의 `backend/store.py` `command()`를 읽기 전용으로 확인했다. 서버는 명령을 받으면 같은 트랜잭션에서 상태를 바꾸고, `command_id`가 담긴 사건(`run_state_changed`, `approval_decided`, `changes_requested`)을 저장한 뒤 202를 돌려준다. 그래서 같은 명령 ID 사건을 반영 근거로 쓸 수 있다.
- **고친 내용**: 버전 기반 해제 조건을 삭제했다. 확인 표시는 같은 `command_id` 사건이 오거나 시간이 초과할 때만 풀린다.
- **테스트**
  - 버전 증가로 해제를 기대하던 기존 테스트를 바로잡았다.
  - "다른 작업으로 `state_version`이 올라도 확인 표시가 유지된다"와 "다른 `command_id` 사건으로는 풀리지 않는다"를 추가했다.
  - 이전 조건을 잠시 되돌리면 새 테스트가 실패하고, 수정 후에는 통과한다. 전체 120개 통과.
- **남는 의존**: 확인은 서버가 명령 반영 사건에 `command_id`를 넣는 현재 동작에 기대고 있다. 계약 §7에 이 보장이 명시되어 있지 않아 CR-C11로 요청한다.

보류: L2(누락 재동기화의 백오프·최대 횟수), L3(사건 추가 O(n²)). 긴 실행이나 비정상 서버에서만 드러나므로 실제 LIVE 사건 규모를 본 뒤 처리한다.

## 확인하지 못한 것

- 실제 모델·실행기가 있는 LIVE 흐름: 실행 생성 → 기획 → 승인 → 202 뒤 스냅샷 반영, 실제 SSE 재연결·resync
- 실제 프리뷰 iframe과 배포 승인 전송(서버 미연결)
- Firefox·Safari, 실기기 터치, 스크린리더 낭독, 대비 수치 측정, 장시간 Canvas 성능 프로파일
- Playwright E2E: 작성하지 않았다. 화면 흐름은 Vitest 통합 테스트와 수동 브라우저 확인으로 대신했다

## 계약 요청 (새 요청)

**CR-C09 AC 충족 상태**
- 동작: Sprint와 전체 AC 충족 현황을 작업 진행과 구분해 보여준다.
- 부족: Snapshot·PlanView 어디에도 AC별 판정이 없다. 현재 화면은 "충족 판정은 서버가 아직 제공하지 않음"이라고 표시한다.
- 제안: 판정 주체(검증 보고서)에 묶인 `acceptance: [{id, status: "unmet"|"met"|"failed"|"not_run", report_id?}]`
- 호환성: Snapshot 확장이라 protocol 버전 검토가 필요하다. 또는 별도 GET으로 받는다.
- 그동안: 정의 개수만 표시한다.

**CR-C10 preview 아티팩트 본문 형식 확인**
- 동작: 프리뷰 dialog가 `GET /api/artifacts/{preview id}`를 `http.Preview`로 해석한다.
- 부족: 계약 §7은 spec만 PlanView로 명시한다. preview 종류가 `http.Preview`를 반환하는지 명시가 없다.
- 제안: "kind: preview → http.Preview" 한 줄을 명시한다.
- 그동안: 형식이 다르면 "프리뷰 주소 없음"으로 표시하고 열지 않는다.

**CR-C11 명령 반영 사건의 `command_id` 보장**
- 동작: 명령 접수(202) 뒤 "반영 확인 중"을 정확히 끝낸다.
- 부족: 현재 서버는 명령으로 상태를 바꾼 사건에 `command_id`를 넣지만, 계약에는 명시가 없다. `state_version`은 다른 작업도 올리므로 반영 근거가 되지 못한다.
- 제안: "접수된 명령이 만든 공개 사건에는 그 `command_id`를 포함한다"를 계약 §4 또는 §7에 명시한다.
- 호환성: 현재 구현과 같으며, 문서 명시만 필요하다.
- 그동안: 같은 ID 사건이 없으면 20초 뒤 "반영 미확인"으로 조작을 풀어 준다.

## Codex에게 필요한 것 (통합)

1. 이 브랜치 `work/claude-office`의 프론트 커밋을 통합 기준에 병합해 주세요. 프론트 파일은 수정하지 말고, 필요하면 요청으로 남겨 주세요.
2. 루트 README에 `frontend/README.md` 링크와 실행 순서를 추가해 주세요. 순서는 API(8000) → `cd frontend && npm ci && npm run dev`(5173)입니다. 루트 `.gitignore`의 `node_modules/`, `dist/`, `coverage/`가 프론트 산출물을 이미 제외한다.
3. 모델·실행기를 연결할 수 있게 되면 LIVE 흐름 확인 시점을 알려 주세요. 기획 생성 → 승인 → 반영을 프론트에서 확인하겠습니다.
4. CR-C09, CR-C10, CR-C11에 같은 ID로 답해 주세요.

허가 없이 push·merge·deploy를 하지 않았다.
