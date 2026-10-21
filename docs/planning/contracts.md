# 인터페이스 계약

상태: 구현 전 v1 제안. 필드·자료형·열거 값은 [protocol.v1.schema.json](protocol.v1.schema.json)이 단일 원본이다. 이 문서는 전송·권한·의미를 정의한다. 구현 착수 시 FastAPI OpenAPI·프론트 타입·재생 fixture가 이 계약을 따르도록 연결하고 중복 수기 정의를 없앤다.

## 1. 경계와 책임

| 경계 | 입력 → 출력 | 책임 |
|---|---|---|
| 브라우저→서버 | 사용자 명령 → 접수 결과·공개 스냅샷 | 인증·명령 중복·버전·승인 검사 |
| 서버→브라우저 | 공개 이벤트·스냅샷·허용 아티팩트 | 비밀·역할 비공개 자료 제거 |
| Supervisor→역할 | 승인 명세 참조·한 작업·권한 → 아티팩트 참조 | 권한은 서버가 확정, 모델은 변경 불가 |
| 역할→모델 | 문맥 패킷 → 구조화된 작업/패치 제안 | 출력 형식과 허용 도구·경로 검증 |
| 역할→MCP | 역할에 허용된 도구와 입력 → 근거 포함 결과 | 입력·경로·호출 주체·명세 버전 검사 |
| 실행기→Git/배포 | 승인된 operation → 외부 결과·아티팩트 | 중복 방지·상태 조회·실패 보존 |

서버는 클라이언트가 보낸 role·user ID를 권한 증거로 신뢰하지 않는다. 서버 측 인증 세션이 행위자를 결정한다. 외부 공개 시 인증·TLS가 필요하다. 로컬 모드는 loopback 기본, 무인증 공개 바인딩 금지다.

## 2. HTTP 표면 제안

| 경로 | 기능 | 계약 |
|---|---|---|
| `POST /api/projects` | 프로젝트와 최초 원문 생성 | 제목·요청 텍스트만. ID·쓰기 경로는 서버 발급 |
| `POST /api/projects/{id}/runs` | 새 실행 생성 | LIVE/REPLAY 명시 선택. LIVE는 공급자·실행기 선확인 |
| `GET /api/runs/{id}` | 권한별 스냅샷 | 스키마의 Snapshot |
| `POST /api/runs/{id}/commands` | 승인·수정·중지·재개 | 스키마의 Command, 202 접수. 실제 효과는 후속 이벤트로 확인 |
| `GET /api/runs/{id}/events` | SSE·재접속 | 스키마의 Event, 실행별 연속 seq |
| `GET /api/artifacts/{id}` | 허용 결과 다운로드 | 내부 ID→서버 경로 매핑. 임의 로컬 경로·원격 URL 입력 금지 |
| `GET /api/runtime` | 실행 가능성 | 키 유무 대신 모델·런타임·무료 자격 확인 상태, secret 값 제외 |

생성·환경 진단의 세부 스키마는 준비 단계에서 확정한다. 프로젝트 생성을 위해 클라이언트가 파일시스템 경로·실행 명령·키를 입력하는 방식으로 우회하지 않는다. 현재 JSON 스키마는 실행 스냅샷·명령·이벤트에 한정되며 전체 HTTP API가 구현됐다는 뜻이 아니다.

## 3. 이벤트·스냅샷·재생

- SSE의 `id`는 실행별 seq다. 클라이언트는 `Last-Event-ID`로 이어받고 같은 seq를 중복 반영하지 않는다. heartbeat는 상태 이벤트가 아니다.
- 이벤트는 사건과 아티팩트 참조를 전달한다. 공개 상태는 Snapshot에서 읽는다. 상태 변경 이벤트가 오면 해당 버전 이상 스냅샷을 가져온다. Canvas가 이벤트 요약 문장을 파싱해 상태를 추측하지 않는다.
- 스냅샷은 읽은 시점의 state_version과 last_event_seq를 같은 일관된 읽기에서 반환한다. 스냅샷 후 연결은 해당 seq 이후부터 시작해 유실 구간을 막는다.
- state_version은 업무 상태·승인 대상의 변경 트랜잭션마다 증가한다. seq는 공개 사건 순서이며 같은 상태 버전의 사건도 여러 개 있을 수 있다. 단순 모션·heartbeat 때문에 승인 대상 버전을 바꾸지 않는다.
- seq가 건너뛰면 애니메이션을 멈추고 스냅샷/누락 이벤트를 재요청한다. 스트림 단절을 실행 실패나 자동 완료로 오해하지 않는다.
- 처음에는 이벤트를 보존한다. 향후 정리로 재개 구간이 사라지면 명시적인 재동기화 응답을 주고 최신 스냅샷부터 연결한다.
- REPLAY는 replay_source로 실제 기록의 출처·원래 실행 ID·기록 시점·manifest 해시를 제공한다. 원래 결과·사건 시각을 유지하고 재생용 mode와 원본을 구분한다. 재생 시 외부 명령과 승인은 실행하지 않는다. 새 요청은 새 LIVE 실행을 명시 생성한다. LIVE 오류를 자동 데모로 덮지 않는다.

## 4. 버전·멱등·승인 의미

명령마다 command ID와 expected_state_version을 보낸다. 같은 ID·같은 본문은 최초 접수 결과를 반환하고 부작용을 늘리지 않는다. 같은 ID·다른 본문은 충돌이다. 실행 ID는 URL·본문과 일치해야 한다.

서버는 승인 ID·target digest·현재 명세·현재 후보·현재 환경을 비교한다. plan_digest는 명세·AC·계약·무료 정책·허용 도구·저장소/브랜치·배포 대상의 정규화된 기획 패키지 해시다. target_digest는 승인 대상 객체의 정규화된 해시다. 단순 텍스트 concatenation을 쓰지 않고 정규화 규칙을 구현 전에 고정한다. 클라이언트는 해시를 만들지 않고 서버가 제시한 대상을 그대로 승인한다.

스키마만으로 검증할 수 없는 서버 불변식:

- ID 참조는 같은 프로젝트·실행에 속하고 존재해야 한다. task 의존성은 순환이 없어야 한다.
- review_report_ids의 두 개는 validator·security 각 하나이며 같은 명세·커밋·이미지를 검토하고 필수 기준을 충족해야 한다.
- 승인 상태의 행위자·시각은 서버가 기록한다. pending에는 결정 메타데이터가 없어야 한다.
- 배포 이미지와 검사한 코드·환경의 연결이 확인되어야 한다. 문자열 형식이 맞는 digest만으로 안전성이 생기지 않는다.
- 기획 승인 전 구현, 배포 승인 전 배포, REPLAY의 외부 부작용은 서버에서 거절한다.
- 변경 요청이 기획 범위를 바꾸면 implementation으로 표시돼도 명세 재승인을 요구한다. Supervisor의 분류가 권한 검사를 대체하지 않는다.

서버 저장은 프로젝트·실행·원문/명세 버전·Phase/Sprint/Task·시도·승인·검토 보고서·아티팩트·이벤트·외부 operation·작업 lease를 구분한다. 이는 공개 API 필드를 중복 정의하는 새 계약이 아니라 내부 영속화 범위다. 원문/승인/검토/외부 결과는 append-only 이력을 보존하고 변경 대상에는 새 버전·해시를 발급한다. secret은 이 원장과 공개 아티팩트에 저장하지 않는다.

실행기 내부 레코드에는 쓰기 경계·입력 커밋·문맥 패킷·모델/도구 버전·외부 결과 조회 키가 필요하다. 공개 Snapshot은 이 내부 권한 데이터를 전부 노출하지 않는다. 스키마의 큰 의미·열거 값·필수 필드 변경은 프로토콜 버전과 소비자 호환성을 함께 검토하고 fixture/타입을 같은 변경으로 갱신한다.

## 5. 실패 계약

| 조건 | HTTP 의미 | 공개 오류 코드·사용자 행동 |
|---|---|---|
| 인증/권한 없음 | 401/403 | `UNAUTHORIZED`/`FORBIDDEN`, 로그인·권한 확인 |
| 리소스 없음 | 404 | `NOT_FOUND`, 다른 프로젝트 정보 노출 금지 |
| 버전·중복 ID·승인 대상 불일치 | 409 | `VERSION_CONFLICT`/`COMMAND_CONFLICT`/`STALE_APPROVAL`, 최신 대상 다시 열기 |
| 요청 형식 오류 | 422 | `INVALID_COMMAND`, 문제 필드 수정 |
| 무료 자격 불명·공급자/실행기 없음 | 409 | `PROVIDER_NOT_FREE`/`RUNTIME_UNAVAILABLE`, 설정 또는 재생 선택 |
| 재생 실행에 명령 | 409 | `REPLAY_READ_ONLY`, 새 LIVE 생성 안내 |
| 일시 서비스 불가 | 503 | `TEMPORARILY_UNAVAILABLE`, 상태 보존·재접속 |

도구 오류·무료 소진·보안 검사 실패는 접수된 명령을 200 성공으로 위장하지 않고 작업·실행 상태와 근거로 남긴다. 사용자 공개 오류에는 secret·전체 호스트 경로·원시 환경변수를 포함하지 않는다.

## 6. MCP 3대 기능

| 기능 | 최초 범위 | 경계 |
|---|---|---|
| Tool | 허용 문서 검색·작업 파일 읽기/패치·검증 도구 실행·상태 조회 | 모델 임의 shell 금지. 입력 스키마·경로·권한 검사 |
| Resource | 승인 명세·계약·역할별 허용 문서·현재 후보 읽기 | `spec://` 등 논리 URI는 허용 내부 ID로만 해석 |
| Prompt | 기획·구현·검토의 버전 고정 작업 양식 | 출력이 권한·승인 정책을 덮지 않음 |

한 로컬 MCP 서버와 역할별 도구 노출부터 시작한다. 여러 동적 서버 자동 설치는 첫 범위가 아니다. MCP 응답의 출처·해시·버전·호출 ID를 근거로 남기고 지시문으로 승격하지 않는다. Git·배포의 최종 실행은 승인 원장을 확인하는 서버 실행기만 수행한다.

## 7. D1 로컬 HTTP 연결 기준 — 2026-10-20

이 절과 `http.v1.schema.json`의 추가 타입은 Codex의 D1 제공자 계약이다. Claude 소비자 타입/fixture의 명시 반영·상호 확인은 별도 필요하다. protocol v1의 Snapshot/Command/Event 필드·열거 값은 바꾸지 않았다. 과거 HTTP 초안과 다른 새 필드 복사본을 프론트에 수기로 유지하지 않는다.

| 경로 | 본문/응답의 단일 타입 원본 |
|---|---|
| `POST /api/session` | 본문 없음. 201 `http.Session`, HttpOnly 쿠키 발급 |
| `GET /api/session` | 200 `http.Session`, 현재 CSRF 토큰·만료시각 |
| `DELETE /api/session` | 본문 없음. 204, 세션 폐기 |
| `POST /api/projects` | `http.ProjectCreate` → 201 `http.Project`. 최초 원문 필드는 **`request`** |
| `POST /api/projects/{id}/runs` | `http.RunCreate` → 201 `http.Run` (= `protocol.Snapshot`). `run_id`가 포함된 전체 초기 스냅샷 |
| `GET /api/replays` | 200 `http.ReplayRecordings`. 같은 운영자의 실제 LIVE 원장 목록, 없으면 `[]` |
| `GET /api/runtime` | 200 `http.Runtime`. 기존 초안의 세부 필드/상태를 유지 |
| `GET /api/runs/{id}` | 200 `protocol.Snapshot` |
| `GET /api/runs/{id}/acceptance` | 200 `http.AcceptanceStatus`. 현재 명세의 AC별 판정과 근거 report ID. 두 검토 수집 전에는 `unmet`이며 미확정 단일 판정을 공개하지 않음 |
| `POST /api/runs/{id}/commands` | `protocol.Command` → 202 `http.CommandReceipt`. `status: accepted`, 완료 의미 아님 |
| `GET /api/artifacts/{id}` | `kind: spec` → `http.PlanView`, `kind: preview` → `http.Preview`. 다른 종류는 해당 산출물 JSON; 임의 HTML 실행/경로 다운로드 없음 |
| `GET /api/environments/{id}` | 환경 미설정이므로 현재 404 `http.Error`. 환경 연결 시 `http.Environment` |
| `GET /api/contracts/{name}` | 번들된 두 스키마의 원문. schema 내 상대 참조를 같은 경로에서 해석 |

모든 오류 JSON은 `http.Error` 형태다. 409 버전 충돌에는 `error.current_state_version`을 포함한다. 404와 잘못된 메서드도 `detail` 대신 이 형태로 반환한다. `request_text`, `accepted: true`, runtime 항목 배열은 이번 D1에서 채택하지 않았다. 위 스키마의 실제 필드를 소비한다.

접수된 명령이 만든 공개 상태 변경 사건에는 해당 `command_id`를 반드시 포함한다(CR-C11). 명령/receipt·상태·사건·후속 작업 예약은 한 SQLite 트랜잭션에 저장하고 commit 뒤에만 202를 반환한다. SSE 사건은 POST 응답보다 먼저 도착할 수 있다. 같은 ID/같은 본문의 재시도는 같은 receipt를 반환하며 새 사건/작업을 중복 생성하지 않는다. 이때 원래 사건의 ID는 그대로 보존한다. 거절된 명령은 접수 사건이 없다. 무관한 worker 사건이나 `state_version` 증가를 내 명령의 반영 확인으로 사용하지 않는다. 명령 접수 상태 확인과 후속 구현/배포 완료는 별개다.

### 로컬 브라우저 세션 (CR-C01)

- 서버는 `python -m backend`로 `127.0.0.1`에만 바인딩한다(기본 8000, `LIFECYCLE_PORT` 1024–65535). proxy 헤더를 신뢰하지 않으며 원격 주소·다른 Host·허용하지 않은 Origin을 거절한다. 외부 공개용 인증은 아직 제공하지 않는다.
- 프론트 주소는 **`http://127.0.0.1:5173`**이다. Vite가 `/api`를 `http://127.0.0.1:8000`으로 프록시한다. 프록시를 사용하는 같은 origin 요청이므로 CORS를 열지 않는다. `localhost:5173` Origin은 이번 허용 목록에 없다.
- 제출본은 빌드된 신뢰 사무실 `frontend/dist`를 API의 `/`에서 제공할 수 있다. 이 경우 요청의 loopback Host와 정확히 같은 Origin도 허용한다. 임의의 다른 포트/Origin을 허용하거나 CORS를 열지 않는다. 별도 포트의 세션 쿠키 이름을 분리하되 HttpOnly/CSRF 조건은 그대로 유지한다. import는 생성 코드나 프리뷰를 이 경로에 설치하지 않는다.
- 브라우저는 `POST /api/session`으로 연결한다. 정확히 허용한 로컬 Origin을 검사한 후 8시간짜리 무작위 세션을 `HttpOnly; SameSite=Strict; Path=/api` 쿠키로 발급한다. 자격 증명을 입력하거나 번들·URL·localStorage에 넣지 않는다. CSRF 토큰은 JSON으로 받으며 메모리에서만 보관한다.
- 이후 POST/DELETE 등 변경 요청에는 `X-CSRF-Token`과 같은 Origin이 필요하다. EventSource는 쿠키로 인증한다. 새로고침 시 `GET /api/session`으로 CSRF를 읽고, 401이면 다시 로컬 연결한다. 서버 재시작 시 세션은 폐기된다. 로그아웃/만료 뒤 SSE도 종료한다.
- 이 흐름은 신뢰한 로컬 origin/프로세스를 운영자로 취급하는 개인 로컬 모드다. 공용 서버·다중 사용자 로그인은 아니다. 기존 CLI Bearer 인증은 서버 설정 `LIFECYCLE_TOKEN`으로만 남긴다. 미설정 시 서버 메모리에서 무작위 생성하며 출력하지 않는다.
- 생성 앱 프리뷰는 `http://localhost:<서버 할당 포트>`를 사용하고 호스트에는 `127.0.0.1`로만 바인딩한다. 운영자 화면은 `127.0.0.1:5173`이다. 다른 hostname과 sandbox iframe(allow-same-origin 없음)으로 부모 쿠키를 격리한다. 프록시는 opaque iframe의 `Origin: null` CORS만 허용하며 credentials를 허용하거나 전달하지 않는다. REPLAY에서는 외부 프리뷰 iframe을 열지 않고 주소·커밋의 기록만 표시해야 한다.

### SSE cursor와 heartbeat (CR-C05)

최초 연결은 `/api/runs/{id}/events?after=<snapshot.last_event_seq>`. 재접속은 `Last-Event-ID`가 있으면 쿼리보다 우선한다. cursor는 0 이상의 16자리 이내 십진 정수다. 누락/형식 오류는 422 `CURSOR_INVALID`, 없는 실행은 404다. 현재 이벤트는 삭제하지 않고 모두 보존한다.

공개 사건은 `id: <seq>`, `event: lifecycle`, `data: <protocol.Event JSON>`이다. 약 15초 무사건 시 `: heartbeat` 주석을 전송한다. 현재 기록 범위 밖 cursor는 200 SSE로 `event: resync`, `data: {"reason":"cursor_out_of_range"}` 한 건을 보내고 연결을 닫는다. 프론트는 기존 EventSource를 닫고 Snapshot을 다시 읽어 새 cursor로 연결한다. heartbeat·resync는 protocol.Event로 파싱하지 않는다. 단절 시 자동 성공/실패로 표시하지 않는다.

### 기획·해시·미연결 기능 (CR-C06–C08)

`kind: spec` 아티팩트는 `http.PlanView`다. 목표·기능·비범위·AC 정의·가정·원문 대비 변경 설명·제약과 서버 소유의 스택·도구·저장소/배포 대상·무료 정책·계약/템플릿/검사 입력 해시를 포함한다. `contract_digests`는 두 JSON 계약·템플릿 계약/lock·Dockerfile·보호된 검사의 상대 경로를 키로, 원본 바이트 SHA256을 값으로 가진다. 입력 변경 후 옛 승인은 거절되며 재기획이 필요하다. 저장소·배포 대상 `null`은 미설정이며 외부 부작용을 허용하지 않는다. 최초 요청/정정 원문은 원장에 보존한다. 모델의 `changes`는 설명이지 원문 대조 검증 결과가 아니다. AC 이행 상태는 별도 AcceptanceStatus로만 제공하며 ID/정의만으로 충족을 표시하면 안 된다.

정규화는 `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`의 UTF-8 바이트다. 문자열 Unicode는 정규화하지 않고 원문 코드포인트를 보존한다. `plan_digest`는 서버가 기록한 PlanView의 SHA256, `target_digest`는 승인 target 객체의 SHA256이다. 브라우저가 해시를 다시 만들지 않는다.

현재 Sprint는 프론트가 running/ready 작업에서 도출하고 도출임을 표시한다. 중지는 명령 접수와 실제 Snapshot으로 확인한다. worker와 MCP 권한은 명세/상태 버전·시도·lease를 재검사해 중지/변경 이전의 쓰기·늦은 결과를 반영하지 않는다. 프리뷰 operation은 서버가 발급한 컨테이너 이름·이미지와 상태를 조회해 재개한다. 외부 Git/배포 operation은 미구현이다.

현재 LIVE는 작은 문의 CRUD 템플릿의 기획→승인→MCP 파일 패치→고정 Git 후보/이미지→독립 기능/보안 검사까지 연결한다. 두 검토가 같은 후보에서 pass일 때만 프리뷰를 발급한다. 스캐너/DB 미준비·만료·오류는 통과가 아니다. 보안 취약점은 실제 검사 결과에 따라 출시를 막는다. 실제 배포는 비활성이다.

프리뷰 상태의 `scope: implementation` 요청 중 명시적인 색·여백·폰트·레이아웃 변경만 CSS 쓰기 권한을 가진 새 Sprint로 보낸다. 기존 기획 승인은 유지하고 검토·출시 승인은 무효화한다. 기능/API/데이터/권한 변경 및 모호한 요청은 원문을 보존하고 재기획·재승인한다. 수정 후보는 같은 두 검토를 새로 받아야 한다.

같은 명세의 프리뷰 교체는 기존 데이터 볼륨을 유지한다. 다른 명세는 새 볼륨을 사용하고 이전 볼륨을 보존한다. 새 후보의 health·발급을 확인한 후 옛 프리뷰 컨테이너·네트워크를 정리하며 데이터 볼륨은 자동 삭제하지 않는다. 임의 DB 스키마 간 자동 데이터 이전은 제공하지 않는다.

### S04–S05 공개 근거 (CR-C12)

추가 HTTP 정의이며 protocol/Snapshot/명령 필드는 바꾸지 않는다. 소비자가 계약 전용 커밋의 타입/해시를 반영한 뒤 공개 artifact 연결을 활성화한다.

- `kind: retrieval` → `http.RetrievalEvidence`. `method`는 실제 실행한 keyword/semantic, `status`는 found/no_results/search_error다. 오류를 빈 결과로 바꾸지 않는다. `model`은 사용한 로컬 embedding 식별자이며 키워드면 null이다. sources에는 역할 ACL을 통과한 최대 5개 chunk의 출처 URL·문서 버전·라이선스·최초 수집 시각·본문 해시·역할 ACL·관련도를 제공한다. 점수는 충족/검사 판정이 아니다. `search_error`의 error_code는 공개된 안전한 분류만 사용하며 내부 예외/모델 prompt는 제공하지 않는다. 상대 검토 원문/판정은 코퍼스에 넣거나 공개하지 않는다.
- `kind: context` → `http.ContextEvidence`. 원문 source_digest와 원장의 request_id/offset/length/chunk hash, 완료/전체 조각 수, 명세 버전 및 ready/needs_input을 제공한다. offset/length는 Unicode 코드포인트다. 원문/정정은 원장에 그대로 남고 역할별 필수 조건은 직접 입력한다. 압축 근거는 내부 사고 원문이나 승인 증거가 아니다. 공개 본문에는 raw prompt/추론/파일 내용이 없다. 완료 조각 수는 total을 넘지 않으며 source_digest 변경 시 이전 checkpoint를 새 입력으로 재사용하지 않는다.

`ReplayRecording.recorded_at` 및 동결 `replay_source.recorded_at`은 포함된 원본의 마지막 사건 occurred_at이다(CR-C13). GET/재생 생성 시각이 아니며 원본에 새 사건이 없으면 조회 결과가 안정적이다. LIVE 기록의 최신 사건이 바뀌어도 생성된 REPLAY의 시각/manifest는 변하지 않는다.

### S12 실제 기록 이동 (CODEX-RECORDING-001)

소비자 타입 반영을 확인한 뒤 등록한 계약: `GET /api/runs/{id}/recording` → `http.RecordingBundle`; `POST /api/recordings/import`(동일 세션/CSRF, 최대 16 MiB JSON) → `http.RecordingImportResult`. 같은 manifest의 import는 같은 읽기 전용 run을 돌려주며 원본 기록/기존 실행을 덮어쓰지 않는다. 파일/모델/키가 없는 별도 환경의 기록 열람용이다. 생성 코드·외부 URL·명령·승인·배포를 실행하지 않는다.

Bundle은 동결 snapshot/events와 거기에 참조된 **공개** artifact 원본만 포함한다. jobs/attempt prompts/requests 원문/토큰/grants/환경변수/DB 파일·모델 가중치는 포함하지 않는다. `manifest_digest`는 이 필드를 제외한 bundle의 canonical digest다. metadata/report hash·명세/후보 결속·이벤트 순서와 계약을 검증하며 비밀 형식/개인 호스트 경로가 검출되면 내보내기를 거부한다. 원본 증거를 몰래 수정해 해시만 바꾸지 않는다. `exporter`는 내보내기 코드/계약/Python 버전이며 과거 원장 생성 당시 버전이라는 뜻이 아니다. 원본 계획의 contract_digests는 그대로 남는다.

`ReplayRecording.provenance`, `ReplaySource.provenance`는 선택적 추가 필드다. 없으면 기존 local_ledger 기록이다. import 결과와 재생에는 `imported_unsigned`를 보존한다. UI는 **가져온 기록(서명 없음)**을 로컬 원장/새 LIVE와 구분하고 프리뷰 iframe·승인·실행을 금지한다. 해시는 훼손 검출이며 원장 출처의 서명/검토 진위 보증이 아니다. import된 승인/보고서를 LIVE 출시 권한으로 재사용하지 않는다.


### POST-INTEGRATION / CR-C15 출시·복구 공개 근거

`GET /api/runs/{id}/release` → `http.ReleaseView`를 추가한다(기존 세션/읽기 전용). 현재 `enabled=false`이며 승인·push·배포·복구 실행 엔드포인트를 뜻하지 않는다. 실제 대상/기획·출시 승인 전 외부 작업은 비활성이다. 202 접수나 예시를 실제 완료로 바꾸지 않는다.

- `unconfigured`는 등록된 manifest가 없음, target/details는 null·operations는 빈 목록이다. reason으로 준비 조건을 설명한다.
- manifest가 있으면 `target`은 저장된 정확한 ReleaseTarget이며 details는 저장소/branch·push 자동 배포 여부, 환경, registry 참조, 확인한 무료 정책, 첫 출시 공개 중단/볼륨 보존 계획이다. candidate 호스트 경로·키·내부 쓰기 권한은 제공하지 않는다.
- operations는 서버 원장에 보존한 operation_id/action(push/deploy/rollback)/state다. 단순 GET으로 공급자 재조회나 재실행을 하지 않는다. accepted는 서버의 실행 의도 기록(SQL pending에 대응), applied는 어댑터가 실제 조회로 확인했던 결과, uncertain은 불명이며 자동 재실행/성공으로 바꾸지 않는다. not_applied/superseded도 성공이 아니다.
- state는 마지막 공개 원장 결과를 요약한다. rollback applied의 rolled_back은 이 어댑터에서 **첫 출시 서비스 공개 중단과 볼륨 보존**이며 이전 버전/DB 복원을 뜻하지 않는다. 실패·응답 유실은 reason/원장 상태 그대로 보여준다.
- 재생은 동결된 공개 deployment artifact가 있으면 그 기록만 표시하고 실행은 계속 불가다. 기록이 없으면 unconfigured다. GET 결과를 새 LIVE 승인 권한으로 재사용하지 않는다.

### Runtime 보조 정보 (CR-C14 기획별 지원 공백을 대체하지 않음)

`Runtime.template_id`와 `data_source_status`를 선택적 추가한다. 기존 소비자는 무시할 수 있다. template_id는 운영자가 선택한 고정 requests-v1/cafemap-v1 기본값이며 각 실제 run의 프로필은 생성 시 서버가 불변으로 기록한다. requests-v1은 data_source_status=not_required, cafemap-v1은 현재 unconfigured다. `live_available=true`는 로컬 모델/worker가 준비됐다는 뜻이며 외부 지도 검색·추천/프리뷰 수용 성공이 아니다. 외부 데이터는 사용자 결정으로 보류했고 `external_api_enabled=false`, 공급자/키/좌표 전송은 없다. reason에 지원 공백과 실제 승인 전 확인할 조건을 제공한다.

카공지도 앱은 기존 opaque sandbox를 풀어 위치 권한을 우회하지 않는다. 위치는 명시 동의와 secure origin 경로를 별도로 준비해야 하며 거절/미지원 시 수동 위치 입력을 유지한다. 실제 지도/장소 데이터가 없는 상태에서 가짜 장소·CRUD를 수용으로 제시하지 않는다.


### CR-C14 기획별 지원 공백·외부 의존

Claude가 먼저 부여한 원래 번호를 유지한다: **CR-C14는 기획 지원 공백**, **CR-C15는 출시·복구 결과**다. 8ff4ca1의 번호 배정은 잘못됐으며 이 정정 계약이 대체한다. Runtime 템플릿 상태만으로 CR-C14를 충족했다고 판단하지 않는다.

`PlanView.support` → 선택적 `http.PlanSupport`를 추가한다. 기존 기록에 없으면 "지원 정보 미제공/미확인"이며 지원 완료로 추정하지 않는다. 새 제공자는 각 기획에 서버 계산 값을 저장한다.

- template_id, spec_version_id, request_digest는 **그 기획을 만든 요청 원문/정정 묶음과 명세**에 결속된다. 다른 기획/실행의 support를 재사용하지 않고 현재 Runtime 상태로 덮지 않는다. support 본문은 승인할 PlanView digest에 포함되고 재생/export/import에도 동결된다. 소비자는 spec_version_id 불일치 시 표시/승인을 막고 다시 읽는다.
- unsupported는 요청했으나 현재 지원되지 않는 기능의 실제 request_quote·reason·requires를 제공한다. non_goals와 분리한다. 원문/정정은 원장에 보존하며 모델이 임의로 요청을 축소해 공백을 없애지 않는다.
- external은 provider(미정은 null), purpose, needs(무료 자격/키/쿼터/attribution/위치 동의/격리 경로), status(unconfirmed/confirmed/deferred), reason이다. 사용자 선택 "외부 연결은 나중에 결정"은 deferred이며 무료 자격/공급자 연결을 확정으로 표시하지 않는다. 브라우저 위치 동의와 외부 공급자로의 위치 전송 승인은 별개다.
- implementation_allowed=false면 현재 공백 때문에 구현 승인이 불가하다. 프론트는 공백과 필요한 입력을 별도 구역에 표시하고 기획 approve를 막는다. 서버도 같은 저장된 support를 검사해 INVALID_STATE로 거절하며 승인/작업 예약을 만들지 않는다. reject/수정 요청은 유지한다. true는 알려진 지원 공백이 없다는 뜻이며 AC 충족·검토/출시 수용 성공이 아니다. 실제 승인은 여전히 사용자가 한다.

CR-C15 operations는 accepted/applied/uncertain/failed/rolled_back/not_applied/superseded를 구분한다. accepted_at은 실행 의도를 저장한 시각, observed_at은 실제 공급자 조회가 완료된 시각이며 과거 원장에 없으면 null이다. GET 시각으로 만들지 않는다. reason은 응답 유실/미확인 등의 안전한 근거이며 내부 예외/키를 노출하지 않는다. volume_preserved는 실제 볼륨 조회를 확인한 경우만 boolean이고 미확인이면 null이다. true도 데이터 내용/DB 이전 검증을 뜻하지 않는다. target에 환경 설정 해시·commit·registry digest·두 보고서·rollback hash가 결속된다. 관련 공개 사건은 operation_id와 공개 artifact_ids로 같은 결과를 연결하며 상대 미확정 검토는 포함하지 않는다.


### CR-C14 후속 — 카카오 선택·무료 정책 호환

사용자가 카카오맵으로 테스트하고 외부 연결 보류를 해제했다. 기존 번호는 유지한다. **CR-C14=기획별 지원 공백**, **CR-C15=출시/복구**이며 새 번호를 재배정하지 않는다. 새 기획의 support.external은 provider=kakao/status=unconfirmed다. 계정의 무료 쿼터 배지 확인이 어렵다는 실제 답변을 반영하며 무료 자격/키·위치 동의·격리 연결 검증과 구현 승인은 미완료다. 옛 기획의 deferred 기록은 그대로 보존한다.

PlanView.free_policy가 기존에는 모든 외부 API를 금지하는 단일 상수였다. 외부 모델 API 금지와 검증된 무료 지도 데이터 사용을 구분하도록 **기존 문구와 새 문구 두 값만 허용하는 enum**으로 확장한다. 새 문구는 `Inference: local Ollama Qwen/DeepSeek only; no paid fallback or external model API. External data: verified free terms, explicit consent, fixed isolated access, no paid overage.`다. 과거 기록의 문구는 수정하지 않는다. 임의의 정책 문자열·유료 모델·유료 초과 사용을 허용하지 않는다.

소비자는 기존처럼 서버의 free_policy를 그대로 표시하고 타입/hash를 재생성한다. 다른 필드/경로 변경은 없다. 새 기획 공개는 소비자 채택 뒤 진행한다. 공급자 선택이나 키 준비를 사람의 기획/배포 승인으로 사용하지 않는다. 키와 계정 확인은 로컬 비공개 설정이며 모델 입력/공개 계약/기록으로 전달하지 않는다.

### CR-C16·CR-C17 일반 시작 프로젝트 ID와 계획 확장 (아이디어 대안·작업 분해·검증 명세)

모두 **선택적 추가**이며 기존 기록과 소비자는 깨지지 않는다. 필드가 없으면 "미제공/미확인"이고 지원·검증이 있다고 추정하지 않는다.

**CR-C16** `Runtime.template_id`, `PlanSupport.template_id`는 고정 enum이 아니라 패턴 `^[a-z0-9][a-z0-9-]{0,62}$` 문자열이다. 서버가 시작 프로젝트 ID를 데이터로 읽고, 특정 과제 이름은 계약에 들어가지 않는다. 옛 기록의 `requests-v1`·`cafemap-v1`은 패턴을 만족한다.

**CR-C17** `PlanView`에 다음 선택 필드를 추가한다.

| 필드 | 뜻 |
|---|---|
| `alternatives` (1–3) | 아이디어 대안 `{id, summary, differences, risks}`. 기획 승인 화면에서 차이·위험을 보여 준다 |
| `selected_alternative_id` | 이 기획이 구현하는 대안. 승인 대상(`plan_digest`)에 포함되므로 선택이 승인에 결속된다 |
| `single_alternative_reason` | 대안이 하나뿐일 때 그 이유(서버 규칙: 대안이 1개면 필수) |
| `work_plan` | 작업 분해 `{id, kind, title, depends_on, acceptance_ids, write_scope}`. 서버 Supervisor가 순환·없는 ID·겹친 쓰기 범위·AC 미연결을 검사한다 |
| `omitted_areas` | 필요하지 않아 생략한 영역과 이유(예: AI/Data) |
| `verification` | 선언형 점검 명세 `CheckSpec`: `http`(요청/기대 상태·JSON 일부), `command`(argv/기대 종료·출력), `file`(존재·내용). 코드가 아니라 데이터다. AC는 `ac_ids`로 연결한다 |
| `manual_acceptance` | 자동 검증 없이 사람이 확인하기로 명시한 AC `{ac_id, reason}` |
| `dependencies` | 승인된 의존성 범위 `{pip:[], npm:[]}`. 범위 밖 설치는 자동 허용되지 않고 사용자 입력이 필요하다 |
| `tool_policy_digest` | 서버가 계산한 도구 정책 digest. 모델이 채우지 않는다 |

의미 규칙(서버가 강제): 점검도 `manual_acceptance`도 없는 AC가 있으면 `PlanSupport.implementation_allowed=false`이며 승인 버튼은 막힌다. 다른 대안을 고르려면 `ChangePayload.alternative_id`를 담은 `request_changes`(scope=spec)를 보내고, 서버는 직전 초안을 `prior_draft`로 유지한 채 그 대안으로 다시 기획한다. 새 승인은 새 `plan_digest`를 만든다. 점검 명세·작업 분해·의존성은 승인된 `plan_digest`에 포함되므로 승인 후 변경은 재기획이다.

`ChangePayload.alternative_id`(protocol)는 선택적 추가다.
