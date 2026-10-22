# 개발 전주기 자동화 에이전트

기준일: 2026-10-20 · **개발 5 Phase·12 기준 Sprint, 첫 로컬 통합 후 미완료 추적 중** · 과제 2안의 별도 신규 프로젝트

문제 입력 → 아이디에이션 → 기획 승인 → 인프라·백엔드·프론트·AI/Data 구현 → 독립 검증·보안 점검 → 사용자 프리뷰·수정 → Git 커밋·푸시 → 승인된 배포까지 연결한다. 사용자는 사무실 화면에서 Phase·Sprint·작업·결과와 근거를 확인한다.

개발을 위한 오케스트레이터라는 정체성을 인정한다. 기존 개인 Orchestrator와 별도로 만들며, 차별점은 승인 명세 유지, 실제 산출물, 독립 검토, 수정·복구와 배포의 연결에 둔다. 과제에서는 작은 업무 앱 하나의 실제 완주로 설명한다.

## 문서 지도

| 문서 | 관리하는 사실 |
|---|---|
| [새 Claude 관제 인계](docs/handoffs/claude-control-tower.md) | 최신 사용자 정정·관제 지시 오류·개입 내역·구현 상태·역할·다음 점검 |
| [새 Claude 관제 시작 프롬프트](docs/prompts/CLAUDE_CONTROL_TOWER_START.md) | 기존 프론트 CLI와 별도인 새 관제 대화의 시작 지시 |
| [서비스 구현/모델 검증 경계](docs/planning/execution-boundary.md) | 2026-10-21 사용자 정정, 요청별 앱 대필 금지·개입 기록·고정 조건 검증 |
| [요구사항과 대화 반영표](docs/planning/requirements.md) | 확정 조건, 철회·후순위 결정, 제안 범위, 요구사항 ID |
| [아키텍처](docs/planning/architecture.md) | 실행·승인·격리·문맥·RAG·모델·복구 구조와 선택 이유 |
| [인터페이스 계약](docs/planning/contracts.md) | API 경계, 권한·오류·동시성·전송 의미 |
| [프로토콜 스키마](docs/planning/protocol.v1.schema.json) | 명령·이벤트 필드·자료형·필수 항목·열거 값의 단일 원본 |
| [사무실 화면](docs/planning/experience.md) | 정보 구조·장면·상호작용·접근성·Jev 보조 기능 |
| [구현·제출 계획](docs/planning/delivery.md) | 이 제품 개발의 5 Phase·12 Sprint, 담당·의존성·완료/종료 조건·기준 시점 대조·제출 패키지 |
| [수용 시나리오](docs/planning/acceptance.md) | 관찰 가능한 합격·실패 조건. 아직 실행 증거는 아님 |
| [근거와 대조 결과](docs/planning/evidence.md) | PDF·코드·참고 프로젝트·200선·공식 자료와 확인 한계 |
| [협업 프로토콜](docs/planning/collaboration.md) | 향후 구현 서브에이전트 사용 전제·작업·통합·보고 방식 |
| [Codex 구현 프롬프트](docs/prompts/CODEX_IMPLEMENTATION.md) | 백엔드·런타임·계약·격리·통합 담당의 실행 지시 |
| [Claude 구현 프롬프트](docs/prompts/CLAUDE_IMPLEMENTATION.md) | 병렬 사무실 프론트·사용 흐름·실제 API 연결의 실행 지시 |
| [P01–P05 보완 작업 지시서](docs/planning/phase-completion.md) | 기존 구현의 Sprint별 남은 작업·담당·인계·완료 조건과 P04 직접 디자인 지시 시점 |
| [Codex 전체 보완 프롬프트](docs/prompts/CODEX_PHASE_COMPLETION.md) | P01–P05 백엔드·런타임·Infra·계약·통합을 이어가는 작업 지시 |
| [Claude 전체 보완 프롬프트](docs/prompts/CLAUDE_PHASE_COMPLETION.md) | P01–P05 프론트 보완, P04 시작 전 사용자에게 직접 디자인 지시를 받는 흐름 |
| [통합 확인 후 재개 지시](docs/prompts/POST_INTEGRATION_RESUME.md) | 통합 대조 후 개발 대기 해제 범위·LIVE/S09와 P05 잔여 작업·실제 승인 경계 |
| [agy 샌드박스 시험](docs/planning/agy-trial.md) | 합성 DevOps 과제·별도 작업 공간·실행 방법·관제탑 평가 기준 |
| [Codex 공통 준비 인계](docs/handoffs/codex.md) | 원격 저장소·로컬 Git/worktree 준비 상태·Claude 착수 신호 |

같은 사실을 여러 문서에서 따로 관리하지 않는다. 요구사항은 요구사항 문서, 필드와 상태 값은 스키마, 작업 순서는 구현 계획을 수정한다. 스키마는 설계 계약이며 현재 실행 중인 API가 아니다.

## 확정선과 다음 작업

- 모델·API는 무료만. 유료 자동 전환 없음. 기존 OpenAI 키를 호출 허가로 취급하지 않는다.
- 첫 테마는 사무실. 추가 테마와 비교군·Before/After는 후순위다. 기능 검증·보안은 유지한다.
- 초기 전체 시간·재계획·수정 횟수 고정 상한 없음. 사용자 중지·복구·무료 한도 준수는 제공한다.
- 구현·검증·보안은 문맥과 권한을 분리한다. 기획·배포 승인은 정확한 버전에 묶는다.
- 사용자가 연 Codex·Claude CLI가 각각 백엔드·런타임·Infra·통합과 프론트를 담당한다. 별도 관제 대화는 ChatGPT에서 새 Claude 대화로 이관 준비 중이며 실제 수신은 미확인이다. agy 배정과 추가 에이전트 자동 기동은 없다.

개발 Phase/Sprint와 제품이 생성 앱에 부여하는 Phase/Sprint는 각각 [구현 계획 §3](docs/planning/delivery.md)과 [아키텍처 §2](docs/planning/architecture.md)가 정의한다. 개발 계획은 이번에 누락을 보완했으며 이전 작업을 소급 완료로 처리하지 않는다.

최신 구현 근거와 미확인은 [새 관제 인계](docs/handoffs/claude-control-tower.md)를 확인한다. 사용자 지적에 따라 요청별 앱 대필 지시를 정정했다. 기존 카공지도 실행은 수작업 개입이 있는 개발 자료이며 로컬 모델 자율 개발 완주는 미검증이다. 다음은 공통 서비스 기반과 요청별 앱 코드의 개입 범위 점검이다. 이번 문서 보완만으로 작업 세션을 재개하거나 외부 작업을 승인하지 않는다.
