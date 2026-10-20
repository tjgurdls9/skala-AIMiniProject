# 사무실 프론트엔드

개발 전주기(요청 → 기획 승인 → 구현 → 검증·보안 → 프리뷰 → 배포 승인)를 따라가고 조작하는 사무실 화면이다. Vue 3 + Vite + TypeScript이며, 상태 라이브러리·3D 엔진·외부 폰트는 쓰지 않는다.

## 실행

Node 20 이상. 이 문서의 확인 환경은 Node 26.5 / npm 12.0이다.

```sh
cd frontend
npm ci
npm run dev        # http://127.0.0.1:5173, /api → http://127.0.0.1:8000 프록시
```

API 서버는 Codex 담당이다(`backend/README.md`). 브라우저는 반드시 `http://127.0.0.1:5173`으로 연다. 서버는 이 Origin만 허용하며 `localhost:5173`은 허용 목록에 없다. API 없이도 시작 화면의 **합성 예시**는 동작한다.

| 명령 | 내용 |
|---|---|
| `npm run gen:types` | `../docs/planning/protocol.v1.schema.json`, `http.v1.schema.json`에서 `src/generated/*.ts`를 생성한다. 각 파일 옆 `.sha256`에 원본 해시를 남긴다. 생성 파일은 수정 금지 |
| `npm run typecheck` | `vue-tsc --noEmit` |
| `npm test` / `npm run coverage` | Vitest + happy-dom |
| `npm run build` | 타입 검사 후 `dist/`로 빌드 |

## 세 가지 출처

| 출처 | 들어가는 법 | 화면 표시 | 명령 |
|---|---|---|---|
| LIVE | 시작 화면 → 새 요청 (`?run=<id>`) | `LIVE` | API로 보낸다. 202는 접수일 뿐이며, 반영은 이후 스냅샷으로 확인한다 |
| 실제 기록 재생 | 시작 화면 → 실제 기록 재생 | `실제 기록 재생 · 읽기 전용` + 원본 실행·기록 시각·manifest | 보내지 않는다 |
| 합성 예시 | 시작 화면 → 합성 예시 (`?example=<id>`) | `합성 예시 · 실제 실행 아님` | 보내지 않는다(`EXAMPLE_NOOP`). 네트워크를 쓰지 않는다 |

LIVE 배지는 출처가 실제 API이고 `snapshot.mode === 'live'`일 때만 붙는다. LIVE에서 오류가 나도 예시로 자동 전환하지 않는다. 합성 예시(`src/examples/`)는 `replay_source`를 갖지 않으며, 실제 기록인 것처럼 꾸미지 않는다.

## 구조

```text
src/
  generated/      계약에서 생성한 타입 (수기 수정 금지)
  api/            LiveApi(쿠키 세션 + 메모리 CSRF, http.Error, SSE), RunSource 경계
  examples/       합성 예시 시나리오 9종 + 예시 출처
  composables/    useRun(스냅샷·사건·명령), useCommandForm(명령 ID), useDraft(초안 보존), theme
  model/          파생 계산(현재 Sprint 도출·집계·대기 이유·검토 쌍), 알림, 관련도 보조, 라벨
  office/         장면 배치(순수 함수)와 Canvas 그리기
  components/     화면
```

## 동작 원칙

- **인증**: `POST/GET /api/session`의 HttpOnly 쿠키를 쓴다. CSRF 토큰은 메모리에만 두고 변경 요청의 `X-CSRF-Token`으로 보낸다. 401을 받으면 세션을 한 번 다시 연다. 토큰을 번들·URL·저장소에 넣지 않는다.
- **SSE**:
  - 처음에는 `?after=0`으로 연결해 사건 기록 전체를 받는다(서버는 사건을 모두 보존한다).
  - 이미 받은 seq는 버린다. seq가 건너뛰면 마지막 seq부터 다시 연결하고 스냅샷을 다시 읽는다.
  - `event: resync`를 받으면 스냅샷부터 다시 연결한다.
  - heartbeat는 진행으로 보지 않는다. 연결 상태는 실행 상태와 따로 표시한다.
- **스냅샷**: 사건의 `state_version`이 더 크면 스냅샷을 다시 읽는다. 늦게 도착한 이전 버전은 버린다. 요약 문장을 파싱해 상태를 추측하지 않는다.
- **승인**:
  - 서버가 준 `approval_id`·`target_digest`를 그대로 보내며, 브라우저는 해시를 만들지 않는다.
  - 한 결정은 한 명령 ID로 보낸다. 네트워크 재시도는 같은 ID를 쓰고, 409 뒤에는 새 ID를 쓴다.
  - 보내는 중에는 다시 누를 수 없다. 409에서도 의견을 보존하고 최신 대상을 다시 읽는다.
- **프리뷰**: `http.Preview`의 origin이 이 화면과 다른 hostname일 때만 `sandbox="allow-scripts allow-forms"` iframe으로 연다(`allow-same-origin` 없음).
- **장면**:
  - 수신한 공개 사건만 연출한다. 기록 사건은 연출하지 않고, 유휴 동작도 없다.
  - 성공·실패 색은 스냅샷에서 상태가 확인된 경우에만 쓴다.
  - 화면이 숨겨지거나 모션 감소 설정이 켜져 있으면 정적으로 그린다. 같은 내용을 DOM 목록 버튼으로도 제공한다.
- **관련도 보조**: 서버가 준 작업 분야와 의존 관계만 쓰며, 모델을 호출하지 않는다. 강조만 하고 정렬은 바꾸지 않는다. 승인·한도·경고 사건은 항상 보인다.
- **보존되는 화면 상태**: 선택·필터·초안은 스냅샷 교체, 재연결, 테마 전환에도 그대로다. 피드백 초안은 sessionStorage에 두고, 표시 테마만 localStorage에 둔다.

## 남은 한계

- 현재 Sprint와 AC 충족은 서버가 제공하지 않는다. 현재 Sprint는 작업 상태로 도출하고 그렇다고 표시한다. AC는 정의 개수만 보여준다.
- 실제 모델·실행기가 있는 LIVE 기획 생성 → 승인 → 반영 흐름은 브라우저에서 확인하지 못했다(모델 미설정).
- 프리뷰·환경 조회·배포는 서버에 아직 연결되지 않았다. 화면은 "미연결/미설정"으로 표시한다.
