# Claude CLI 인계 — 사무실 프론트엔드

담당: `frontend/**`(의존성·lock·생성 타입·예시 포함)와 이 파일. 백엔드·runner·Infra·공유 계약·루트 파일은 수정하지 않았다. 추가 에이전트는 기동하지 않았다.

## 현재 상태 — 2026-10-20

`FRONTEND_EXAMPLES_AND_LIVE_ADAPTER_READY` — 아래 두 단계를 구분한다.

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
| 프론트 커밋 | `968bbe9` 기반 계층(타입·출처·예시·useRun) / `046f02c` 화면·테스트 / `c7f56a3` 인계 / 코드 리뷰 반영 커밋(아래 절) |

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
| `npm test` (Vitest 5.0.5, happy-dom) | 7개 파일, 119개 통과 (리뷰 회귀 테스트 포함) |
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
| M3 | 접수된 명령의 확인 표시가 무관한 버전 변화로 풀리거나, 영원히 잠길 수 있었다 | 같은 `command_id` 사건이 오면 확인으로 본다. 20초 안에 반영 근거가 없으면 조작을 풀고 "반영 미확인"을 알린다 |
| M4 | 다시 연결이 세션 복구보다 SSE를 먼저 열었다 | 스냅샷(세션 재발급 포함)이 성공한 뒤에만 SSE를 연다 |
| M5 | 작은 버튼이 44px 미만이었다 | 터치 기기(`pointer: coarse`)에서 모든 버튼을 44px 이상으로 했다 |
| M6 | 승인 뒤 여는 버튼이 사라지면 포커스가 body로 떨어졌다 | 작업 공간 `main`(`tabindex=-1`)으로 돌린다 |
| M7 | PlanView를 검증 없이 캐스팅했다 | 필수 필드를 모두 확인하는 공용 가드를 추가했다. 형식이 틀리면 승인을 막는다 |
| L1 | resync 뒤 사건 목록이 커서와 맞지 않았다 | 새 커서 이후의 사건을 버린다. 스냅샷 실패 시 낡은 커서로 연결하지 않는다 |
| L4·L6 | 일시 중지 오류가 남았고, 새 결정 대기가 낭독되지 않았다 | 상태가 바뀌면 오류를 지운다. 새 결정 대기를 polite live region으로 한 번 알린다 |
| L5 | 프리뷰 조회 실패가 미연결 문구로 보였고, 늦은 응답이 끼어들 수 있었다 | 조회 오류는 따로 표시한다. 응답 ID를 확인하고, 로딩 상태도 같은 요청일 때만 끈다 |
| L7 | 실행 생성 재시도 때 프로젝트가 중복 생성됐고, 재생 버튼을 연속으로 누를 수 있었다 | 같은 입력이면 프로젝트를 재사용한다. 재생 버튼은 보내는 중에 막는다 |

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

## Codex에게 필요한 것 (통합)

1. 이 브랜치 `work/claude-office`의 프론트 커밋을 통합 기준에 병합해 주세요. 프론트 파일은 수정하지 말고, 필요하면 요청으로 남겨 주세요.
2. 루트 README에 `frontend/README.md` 링크와 실행 순서를 추가해 주세요. 순서는 API(8000) → `cd frontend && npm ci && npm run dev`(5173)입니다. 루트 `.gitignore`의 `node_modules/`, `dist/`, `coverage/`가 프론트 산출물을 이미 제외한다.
3. 모델·실행기를 연결할 수 있게 되면 LIVE 흐름 확인 시점을 알려 주세요. 기획 생성 → 승인 → 반영을 프론트에서 확인하겠습니다.
4. CR-C09, CR-C10에 같은 ID로 답해 주세요.

허가 없이 push·merge·deploy를 하지 않았다.
