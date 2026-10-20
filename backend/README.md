# 로컬 API·영속 worker

작은 문의 CRUD 템플릿에서 기획→승인→MCP 패치→고정 Git 후보·이미지→독립 기능/보안 검사를 연결했다. 두 검토가 같은 후보에서 통과해야 로컬 프리뷰를 발급한다. 합성 개발 실행에서 기본 이미지 취약점 반려·수정 후 두 검사 통과와 로컬 프리뷰를 확인했다. 스크립트의 테스트 결정은 실제 사용자 승인·제품 전체 완주·실제 배포 완료를 뜻하지 않는다.

Codex worktree 루트에서 실행한다. Python 3.11 이상이 필요하며 이번 확인 환경은 macOS arm64/Python 3.14.7이다.

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.lock
export LIFECYCLE_MODEL=qwen3.5:4b
backend/.venv/bin/python -m backend
```

다른 터미널에서도 같은 worktree 루트와 `LIFECYCLE_DB`를 사용해 실행한다. `LIFECYCLE_MODEL`은 운영자가 확인한 설치된 로컬 Qwen/DeepSeek의 정확한 `name:tag`로 설정해야 한다. 미설정/서버 단절/실행기 lease 없음은 LIVE 불가다. 모델 다운로드·외부 API 전환은 자동으로 수행하지 않는다.

```sh
backend/.venv/bin/python -m runner.worker
```

DB 기본 위치는 제외된 `runtime-data/lifecycle.sqlite3`다. 원문·명세·승인/명령·이벤트·작업·시도/입력 문맥을 저장한다. API와 worker는 별도 프로세스이며, worker lease는 10초·2초마다 갱신한다. 재시작 시 미완료 시도를 보존하고 새 시도로 인계한다. 중지/변경/lease 상실 시 진행 중 모델 요청을 취소하고 늦은 결과를 반영하지 않는다. Ollama 서버 내부 계산이 즉시 중단됐는지는 실제 모델로 별도 확인해야 한다.

브라우저는 `http://127.0.0.1:5173`에서 `/api`를 API의 `127.0.0.1:8000`으로 프록시한다. `POST /api/session`의 HttpOnly 쿠키와 CSRF 토큰을 사용한다. 토큰은 메모리에서만 보관하며 번들·URL·localStorage에 넣지 않는다. 서버 재시작 후에는 세션을 다시 연결한다. 상세 요청/응답·SSE는 [공유 HTTP 계약](../docs/planning/contracts.md)의 7절과 두 JSON Schema가 기준이다.

기획 원문/정정은 2,400 UTF-8 byte 이하 조각으로 순서대로 읽고 위치·해시와 중간 계획을 SQLite에 인계한다. 파일별 구현도 원문 조각과 승인 목표·제약·AC를 직접 제공한다. 호출은 14,000 byte 안에서 준비하며 필수 조건이나 한 파일 자체가 넘으면 원문을 보존하고 `needs_input`으로 분해를 요청한다. 모델의 의미 보존을 자동 보증하지 않으며 실제 계획 승인이 필요하다. 패치는 의도와 입출력 hash를 먼저 저장하고 응답 유실을 실제 파일과 대조한다. 모델의 16,384 문맥/4,096 출력 토큰·120초는 호출별 제한이며 전체 실행·수정 횟수 상한이 아니다. 짧은 LangGraph 호출/SQLite 큐와 원본 스키마·파일 한도 검증을 유지한다.

구현 도구는 실제 stdio MCP로 명세·담당 파일·역할별 문서 검색을 제공한다. 서버가 발급한 시도·lease·상태 버전 권한만 허용하며 임의 shell·호스트 홈·환경·Docker socket을 모델이나 생성 앱에 제공하지 않는다. 기본은 고정 코퍼스 키워드 검색이다. 의미 검색은 운영자가 `ollama pull qwen3-embedding:0.6b`로 설치하고 API/worker 터미널에 `LIFECYCLE_EMBEDDING=qwen3-embedding:0.6b`를 설정한다. 다운로드·유료 전환은 자동 수행하지 않는다. 출처/버전/역할 ACL을 먼저 거르고 벡터 cache는 문서/모델 digest에 묶는다. 버전 충돌·모델 오류를 빈 결과로 숨기지 않는다.

생성/임베딩은 MCP 프로세스와 공통 파일 lock으로 직렬화하고 `keep_alive=0`으로 순차 unload한다. 상주 모델이 남아 있으면 다른 사용자의 모델을 중단하지 않고 자원 대기한다. Ollama 서버도 `OLLAMA_NO_CLOUD=1`, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`로 운영한다. 이 앱 밖의 클라이언트는 앱 lock을 공유하지 않으므로 장비 전체 동시 추론을 보장하지 않는다. 검색/문맥 공개 artifact는 CR-C12 본문과 사건/작업 참조로 연결하며 raw prompt나 상대 미확정 검토는 공개하지 않는다.

격리 실행 이미지와 오프라인 스캐너 DB는 운영자가 먼저 [준비](../infra/README.md)한다. 실행 중 다운로드·패키지 설치·유료 API 전환은 하지 않는다. 프리뷰는 운영자 화면과 다른 hostname의 sandbox iframe이며, 프리뷰의 스타일 수정만 CSS 권한을 가진 구현 Sprint로 보낸다. 나머지 변경은 재승인한다. Git 후보는 로컬 격리 저장소에만 생성하며 원격 push·배포는 비활성이다.

아래 단위/통합 확인은 임시 DB·명시적 fake 모델·mock 도구와 실제 MCP handshake를 사용한다. 별도 합성 개발 실행에서는 실제 Qwen·Docker로 기능 검증 통과/보안 반려를 확인했다. 스크립트의 기획 결정은 실제 사용자 승인으로 취급하지 않으며 테스트 DB는 `runtime-data/`에만 보존한다.

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests -v
backend/.venv/bin/python -m pip check
```

직접 의존성은 `requirements.txt`, 이번 설치의 전이 의존성 핀은 `requirements.lock`이다. 다른 OS/Python의 재설치는 미확인이다. 외부 공개용 로그인/TLS·다중 사용자 지원은 없으며 loopback/Host/Origin 제한을 해제해 공개 서버로 사용하지 않는다.

## 키·모델 없는 기록 열람

프론트 lock으로 `cd frontend && npm ci && npm run build`를 수행한 뒤 worktree 루트로 돌아온다. 제출 패키지에 `frontend/dist`가 있으면 API가 같은 origin에서 사무실을 제공한다. worker/Ollama/Docker는 기록 열람에 필요 없다.

```sh
LIFECYCLE_DB=runtime-data/keyless.sqlite3 LIFECYCLE_MODEL='' LIFECYCLE_EMBEDDING='' LIFECYCLE_PORT=8016 backend/.venv/bin/python -m backend
```

`http://127.0.0.1:8016`에서 기록 파일을 가져온다. 파일은 `lifecycle-recording` v1, 최대 16 MiB다. 해시/계약/명세·보고서·작업 연결을 검사하며 기존 데이터를 덮어쓰지 않는다. "가져온 기록(서명 없음)"의 해시는 훼손 검출용이며 출처 인증이나 실제 사용자 승인 증명이 아니다. 외부 프리뷰·생성 코드·명령·배포는 실행하지 않는다. 공개 기록에는 사용자 입력/산출물이 포함될 수 있으므로 제출 전에 내용을 직접 검토한다. 비밀 형식/개인 호스트 경로가 감지되면 내보내기를 거절하며 원본을 몰래 고치지 않는다.

브라우저의 "기록 파일" 또는 아래 CLI로 내보낼 수 있다. 원본 DB는 read-only로 읽으며 출력 파일이 이미 있으면 거절한다. `exporter`는 내보낸 열람기 버전이며 과거 실행 당시 버전을 보증하지 않는다.

```sh
backend/.venv/bin/python -m backend.archive export --database runtime-data/lifecycle.sqlite3 --run-id RUN_ID --file recording.json
backend/.venv/bin/python -m backend.archive import --database runtime-data/keyless.sqlite3 --file recording.json
```

출시 어댑터 `runner/release.py`는 고정 Git/registry 조회·보호 프록시가 있는 로컬 Docker 환경·첫 출시 unpublish/볼륨 보존에 한정한 내부 구현이다. 실제 대상/무료 자격·권한과 정확한 사용자 승인 연결 전이므로 제품의 배포 API/worker는 비활성이다. cloud 배포·이미지 registry upload·이전 버전 복원/명세 간 데이터 이전은 제공하지 않는다.
