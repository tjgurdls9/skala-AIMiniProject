# SKALA AI Mini Project

기획·개발·독립 검토·사용자 승인·배포를 연결하는 개발 전주기 자동화 에이전트다. 첫 시각화 테마는 사무실이다.

현재 상태(2026-10-22): 시작 프로젝트는 빈 `blank-v1` 하나이고, 기획(아이디어 대안·작업 분해·AC별 점검)·구현·독립 검증과 보안 검사·프리뷰·사람 확인 승인까지 모델이 만든 계획과 승인된 점검으로 서비스가 판정한다. 가짜 모델 테스트(백엔드 342건, 프론트 338건)로 전체 흐름을 확인했다. 실제 모델(qwen3.5:4b)과 실제 Docker로 전체 흐름을 돌린 결과와 그 한계는 `docs/demo/`에 기록한다. 배포 대상(저장소·환경)은 아직 정해지지 않아 실제 배포·원격 push는 비활성이다.

- [전체 기획](DEVELOPMENT_AGENT_DESIGN.md)
- [요구사항](docs/planning/requirements.md)
- [협업 프로토콜과 R&R](docs/planning/collaboration.md)
- [Codex CLI 구현 프롬프트](docs/prompts/CODEX_IMPLEMENTATION.md)
- [Claude CLI 구현 프롬프트](docs/prompts/CLAUDE_IMPLEMENTATION.md)
- [공통 준비 인계](docs/handoffs/codex.md)
- [백엔드·worker 실행](backend/README.md)
- [격리 이미지·스캐너 준비](infra/README.md)
- [사무실 프론트 실행](frontend/README.md)
- [키·모델 없는 기록 열람](backend/README.md#키모델-없는-기록-열람)
- [P01–P05 검증 범위·남은 수용](docs/reports/p01-p05-verification.md)

## 실행 방법

사전 준비(한 번): Docker Desktop과 Ollama를 설치하고 아래를 준비한다. 모델·이미지는 자동으로 내려받지 않는다.

```sh
ollama pull qwen3.5:4b
docker pull python:3.11-alpine python:3.13-slim node:24-slim anchore/grype:v0.121.0
backend/.venv/bin/python -m runner.sandbox prepare          # 프리뷰 프록시 이미지 (결과: runtime-data/runtime-image.json)
backend/.venv/bin/python -m runner.review prepare-scanner   # 취약점 스캐너 DB
```

16GB 장비에서는 시작 전에 여유 메모리 40% 이상, 스왑 2GB 미만인지 확인한다(`infra/dev_checks/memory_guard.py`, 근거 `docs/reports/memory-incident-20261021.md`).

```sh
export LIFECYCLE_MODEL=qwen3.5:4b
export LIFECYCLE_DB=runtime-data/lifecycle.sqlite3
export LIFECYCLE_TOKEN=<32자 이상 임의 문자열>
export LIFECYCLE_PYTHON_IMAGE=$(docker image inspect python:3.13-slim --format '{{index .RepoDigests 0}}')   # python@sha256:...
export LIFECYCLE_NODE_IMAGE=$(docker image inspect node:24-slim --format '{{index .RepoDigests 0}}')         # node@sha256:...
OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 ollama serve &                  # 한 번에 모델 하나
backend/.venv/bin/python -m backend            # API 127.0.0.1:8000
backend/.venv/bin/python -m runner.worker      # 작업 실행기
cd frontend && npm ci && npm run dev           # 사무실 127.0.0.1:5173
```

브라우저에서 `http://127.0.0.1:5173`을 열고 요청을 입력한다. 기획 승인과 사람 확인 승인은 화면에서 사람이 누른다. 화면 사용법은 [사무실 사용법](docs/demo/office-usage.md), 시연 순서는 [시연 스크립트](docs/demo/demo-script.md), 설계 기준과 남은 일은 [공통 기반 설계안](docs/planning/agentic-foundation-design.md)과 [런타임 인계](docs/handoffs/runtime.md)에 있다. 합성 예시와 기록 재생은 모델 없이 화면을 열 수 있다.

사용자가 별도로 운영하는 ChatGPT 대화 세션이 관제탑이다. 이 문서를 읽는 Codex·Claude CLI는 각각 구현 작업 세션이며, Codex CLI는 백엔드·런타임·Infra·통합, Claude CLI는 프론트 담당이다. 세션 간 인계는 사용자가 전달하며 자동 전송을 전제하지 않는다. agy는 이번 구현에 배정하지 않는다. 기록된 agy 과제는 별도의 합성 시험이다.

모델·API는 무료 사용 조건이 확인된 경로만 사용한다. 기획·배포 HITL, 검증/보안의 독립성, 최신 승인 명세 유지가 핵심 조건이다. 비교군과 추가 테마는 후순위이며 초기 전체 실행·수정·재계획 횟수 상한은 두지 않는다.

강의 PDF·베이스 예제·로컬 자격증명·모델 가중치는 이 저장소에 포함하지 않는다. 기획 근거의 일부 로컬 링크는 해당 참고 자료가 있는 개발 환경에서만 열릴 수 있다.
