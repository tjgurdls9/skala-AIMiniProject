# 로컬 API·영속 기획 worker

현재 범위는 기획 생성/승인, 변경 원문 보존/재기획, 중지/재개, SSE, 실제 원장의 읽기 전용 REPLAY다. 승인 뒤 격리 구현기는 아직 연결되지 않아 `waiting_resource`로 기다린다. 생성 앱·독립 검토·프리뷰·배포는 완료되지 않았다.

Codex worktree 루트에서 실행한다. Python 3.11 이상이 필요하며 이번 확인 환경은 macOS arm64/Python 3.14.7이다.

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.lock
backend/.venv/bin/python -m backend
```

다른 터미널에서도 같은 worktree 루트와 `LIFECYCLE_DB`를 사용해 실행한다. `LIFECYCLE_MODEL`은 운영자가 확인한 설치된 로컬 Qwen/DeepSeek의 정확한 `name:tag`로 설정해야 한다. 미설정/서버 단절/실행기 lease 없음은 LIVE 불가다. 모델 다운로드·외부 API 전환은 자동으로 수행하지 않는다.

```sh
backend/.venv/bin/python -m runner.worker
```

DB 기본 위치는 제외된 `runtime-data/lifecycle.sqlite3`다. 원문·명세·승인/명령·이벤트·작업·시도/입력 문맥을 저장한다. API와 worker는 별도 프로세스이며, worker lease는 10초·2초마다 갱신한다. 재시작 시 미완료 시도를 보존하고 새 시도로 인계한다. 중지/변경/lease 상실 시 진행 중 모델 요청을 취소하고 늦은 결과를 반영하지 않는다. Ollama 서버 내부 계산이 즉시 중단됐는지는 실제 모델로 별도 확인해야 한다.

브라우저는 `http://127.0.0.1:5173`에서 `/api`를 API의 `127.0.0.1:8000`으로 프록시한다. `POST /api/session`의 HttpOnly 쿠키와 CSRF 토큰을 사용한다. 토큰은 메모리에서만 보관하며 번들·URL·localStorage에 넣지 않는다. 서버 재시작 후에는 세션을 다시 연결한다. 상세 요청/응답·SSE는 [공유 HTTP 계약](../docs/planning/contracts.md)의 7절과 두 JSON Schema가 기준이다.

기획 문맥이 4,000 UTF-8 바이트를 초과하면 필수 조건을 잘라내지 않고 `needs_input`에 보존한다. 모델의 8,192 문맥/2,048 출력 토큰은 호출별 자원 제한이며 전체 실행·수정 횟수 제한이 아니다. 긴 문맥의 자동 작업 분해, 역할 그래프, RAG/MCP와 격리 도구는 후속 작업이다. LangGraph는 기존 초안의 의존성으로 설치돼 있지만 이번 worker는 아직 이를 호출하지 않는다.

개발 확인은 키·실제 모델·Docker·외부 네트워크 없이 임시 DB와 명시적인 fake 모델만 사용한다. 테스트 데이터는 배포/제출용 LIVE 기록으로 내보내지 않는다.

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests -v
backend/.venv/bin/python -m pip check
```

직접 의존성은 `requirements.txt`, 이번 설치의 전이 의존성 핀은 `requirements.lock`이다. 다른 OS/Python의 재설치는 미확인이다. 외부 공개용 로그인/TLS·다중 사용자 지원은 없으며 loopback/Host/Origin 제한을 해제해 공개 서버로 사용하지 않는다.
