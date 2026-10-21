# SKALA AI Mini Project

기획·개발·독립 검토·사용자 승인·배포를 연결하는 개발 전주기 자동화 에이전트다. 첫 시각화 테마는 사무실이다.

현재는 로컬 모델·격리 구현·독립 검토와 사무실 화면을 연결한 단계다. 합성 개발 실행에서 보안 반려→이미지 수정→두 검사 통과→로컬 프리뷰를 확인했다. 전체 제품 완주나 실제 배포 완료를 뜻하지 않는다.

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

실행 순서는 API(`127.0.0.1:8000`) → worker → `cd frontend && npm ci && npm run dev`(`127.0.0.1:5173`)다. LIVE는 준비한 로컬 Ollama·Docker·스캐너 DB가 필요하고 합성 예시는 모델 없이 화면을 열 수 있다. 실제 배포·원격 push는 아직 비활성이다.

사용자가 별도로 운영하는 ChatGPT 대화 세션이 관제탑이다. 이 문서를 읽는 Codex·Claude CLI는 각각 구현 작업 세션이며, Codex CLI는 백엔드·런타임·Infra·통합, Claude CLI는 프론트 담당이다. 세션 간 인계는 사용자가 전달하며 자동 전송을 전제하지 않는다. agy는 이번 구현에 배정하지 않는다. 기록된 agy 과제는 별도의 합성 시험이다.

모델·API는 무료 사용 조건이 확인된 경로만 사용한다. 기획·배포 HITL, 검증/보안의 독립성, 최신 승인 명세 유지가 핵심 조건이다. 비교군과 추가 테마는 후순위이며 초기 전체 실행·수정·재계획 횟수 상한은 두지 않는다.

강의 PDF·베이스 예제·로컬 자격증명·모델 가중치는 이 저장소에 포함하지 않는다. 기획 근거의 일부 로컬 링크는 해당 참고 자료가 있는 개발 환경에서만 열릴 수 있다.
