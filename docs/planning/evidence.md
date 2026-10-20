# 근거와 문서 대조 결과

기준일: 2026-10-20. 이 문서는 설계 근거·출처·확인 범위를 관리한다. 코드가 있는 것, 문서에 설명된 것, 실제 이 장비에서 검증한 것을 구분한다.

## 1. 권위와 대조 방법

사용자의 최신 명시 지시 → 이번 세션의 이전 확정 지시 → 과제의 실제 요구 → 확인한 코드·참고 구현 → 설계 제안 순으로 충돌을 정리했다. 코드의 현재 동작이 사용자의 새 요구를 무효화하지는 않는다. 강의의 예시 기술·반복 상한은 이번 제품의 의무가 아니다.

이전 외부 답변의 “무조건 1안”, “80% 재사용”, “특정 해커톤 수상”, “점수 보장”, “3일 완성” 등은 검증한 근거 없이 사실로 채택하지 않았다. 주제 탐색의 맥락으로만 [대화 반영표](requirements.md)에 보존했다.

## 2. PDF

페이지는 인쇄 슬라이드 번호가 아닌 **실제 PDF 페이지** 기준이다.

| 자료·위치 | 확인 내용 | 설계에 미친 영향 |
|---|---|---|
| [미니 프로젝트 PDF](../../AI-Mini-Project_20261004_2.pdf), p3 | Day1 선택 과제·계획 등록, Day3 13시 Git 주소·보고서 URL 제출, 17시30분 발표 | Git·결과 보고서·설명 가능한 데모 준비. 현재 실제 남은 시간은 별도 확인 |
| 같은 PDF p10 | 기존 개선 또는 신규 선택, 주제·AI 도구 제약 없음, 본인 코드 설명 필요 | 별도 개발 전주기 에이전트 가능. 도구를 썼어도 구조·한계 설명 |
| 같은 PDF p11–12 | RAG·모듈·서브에이전트·HITL·메모리·Judge·데이터는 예시 | 제품에 필요한 기능으로 연결. 예시를 전부 강제 항목으로 바꾸지 않음 |
| 같은 PDF p13 | 완성도30·기술30·한계/트레이드오프20·발표20, 동일 입력 Before/After 보너스10 | 비교는 사용자 지시대로 후순위. 실제 기능·기술 의미·한계 설명 우선 |
| [253p 캡스톤 강의안](<../../AICapstone resource/AI캠퍼스_AI_Capstone_20261016.pdf>), p18/슬라이드17 | 전담 Validator 채택, 키워드·길이만으로 의미 누락 판단 부족, 매 응답 HITL의 부담 | 검토를 별도 역할로 두고 주요 기획·배포에 HITL. 결정론적 검사도 함께 사용 |

프로젝트 PDF에는 공개 클라우드 상시 운영·API 사용·가중치 동봉 의무가 명시돼 있지 않다. 별도 평가 환경 조건까지 확인했다는 뜻은 아니다. 제출 후 읽기 편의와 LIVE 실행 준비를 구분했다.

캡스톤 강의안은 설계 철학과 예시를 확인했고, 이번 기획에서 253쪽의 모든 문장·그림을 전수 검수했다고 주장하지 않는다. 미니 프로젝트 평가·제출 관련 페이지를 직접 재대조했다.

## 3. 베이스 코드: 재사용과 교체 경계

| 파일·확인 지점 | 실제 상태 | 이 설계의 처리 |
|---|---|---|
| `all_total_vue_student/server.py` | FastAPI·SSE·모델 선택·대화 세션 | HTTP/SSE·DI 패턴 참고. 실제 코딩 실행기를 이미 보유한 것으로 계산 안 함 |
| `agent/deps.py` | fast/quality LLM·MCP·session store 주입 | 주입 방식을 참고하되 유료 fast/quality 기본 모델 정책은 계승 안 함 |
| `agent/graph.py` | route→plan→gate→research→replan→analysis→write→validate | 역할·이벤트 흐름 참고. AIOps 하드코딩을 개발 에이전트로 이름만 변경하지 않음 |
| 같은 파일 `_extract_system_name` | MCP Prompt용 단일 시스템 선택. 실제 조사 대상은 plan의 tasks가 따로 결정 | “첫 시스템만 실제 조사한다”는 외부 답변의 과도한 해석을 교정 |
| 같은 파일 incident 분류 | 키워드와 db-down fallback | 개발 작업 분류의 기본값으로 재사용 안 함 |
| 같은 파일 `research_node` | 병렬 예시용 고정 `sleep(0.35)` 포함 | 제품에서 인위 지연 제거. 이를 실전 속도 증거로 사용 안 함 |
| 같은 파일 `validate_node` | 30자·`1)` 검사, 실패해도 3회 뒤 강제 PASS | 이식 금지. 미충족·불명·미실행을 보존하고 수정으로 연결 |
| 같은 파일 `build_graph` | `compile()`에 checkpointer 없음 | durable 실행·interrupt 복구를 추가 설계해야 함 |
| `agent/session_store.py` | SQLite messages의 대화 이력 | 실행 큐·승인·부작용·체크포인트와 다름 |
| `agent/ollama_llm.py`, `openai_llm.py` | 도메인별 메서드·토큰 기반 비용 계산·일부 동기 HTTP | 개발 작업용 구조화 출력·비동기 경계·무료 정책·실제 비용 표시 재설계 |
| `agent/mcp_client.py` | Tool/Resource/Prompt 탐색·호출 구조 | 발견 패턴 참고. 권한 정책·출력 신뢰 경계 추가 필요 |
| `requirements.txt` | 여러 패키지가 하한 버전 지정 | 재현 가능한 정확 버전 lock과 호환 확인 필요 |

위는 코드 열람 결과이며 실행 통과 결과가 아니다. 코드 위치는 모두 `all_total_vue_student/` 기준이다. 기존 베이스 수정·전체 복사·성능 측정은 하지 않았다.

강의 실습의 `wave04_multi_agent_streaming/followup.md`는 Ollama Qwen 작업 분해의 비결정성을 설명한다. `wave07_dynamic_planning/langgraph/followup.md`는 조건 재계획, `wave08_validator_agent/followup.md`는 mock 검증/재작성, `wave11_latency_parallelization/followup.md`는 sleep 기반 I/O 병렬, `wave12_stateless_session/followup.md`는 SQLite 저장을 설명한다. 예제 결과를 이 제품의 실측으로 인용하지 않는다. 실습 followup과 베이스 구현의 범위도 동일시하지 않는다.

## 4. 사용자 참고 프로젝트

| 위치 | 확인한 것 | 차용·제한 |
|---|---|---|
| `../skala-AIAgent/signal_room/DESIGN.md` | 역할 캐릭터·공개 상태·근거·회의·반응형·키보드·모션·테마 계약 | 업무 지도와 증거 중심 화면으로 확장 |
| 같은 프로젝트 `static/room.js` | 720×430 Canvas·고정 4역할·장면 상태 API·로컬 모션 | 고정 4인 가정은 그대로 복사 안 함. 표시와 런타임 분리 참고 |
| 같은 프로젝트 preview 이미지 | 사무실·dark/light 장면의 시각 방향 | 이번 새 제품 UI 검증 증거로 사용 안 함 |
| `../claude-studio/feed-curator/README.md`, `index.html` | Xenova multilingual-e5-small q8·브라우저 관련도·기사 조판 | Jev 같은 빠른 판단 아이디어의 실제 참고. 공식 Jev 실행과 다름 |
| `../claude-studio/morning-paper/docs/ENGINES.md`, `HOW-IT-WORKS.md` | RSS→구조화 편집→발행, Claude/Codex CLI 엔진 | ID 기반 산출물·단계 기록 참고. 유료/구독 엔진은 무료 전용 제품 경로에 채택 안 함 |

참고 문서의 과거 검수·속도 수치는 해당 앱의 자기 기록이다. 이 장비·새 앱에서 재측정하지 않았다. 형제 프로젝트는 읽기만 했고 수정하지 않았다.

## 5. 200선 검토와 실제 도입 범위

[마스터200선](../../all_total_vue_student/doc/OPENSOURCE_CATALOG_200.md), [RAG100선](../../all_total_vue_student/doc/RAG_OPENSOURCE_100.md), [개발전주기100선](../../all_total_vue_student/doc/ALL_IN_ONE_AGENT_TOOLS_100.md)의 목록을 교차 확인했다. 개별 200개 저장소 코드·라이선스·보안·유지보수까지 감사한 것은 아니다.

| 발견 | 처리 |
|---|---|
| LangChain 항목2와 TextSplitters66이 같은 저장소 링크 | 독립 2개 기술의 채택 증거로 세지 않음 |
| AutoGen (AG2) 명칭이 microsoft/autogen 링크와 혼용 | 실제 채택한다면 프로젝트 정체성부터 재확인 |
| 173 Mockall 링크가 python/cpython | 잘못된 도입 근거로 사용하지 않음 |
| 일부는 조직/범용 저장소 링크·상용 구성 혼재 | 카탈로그 등재를 OSS 라이선스 검증으로 간주하지 않음 |
| 여러 오케스트레이션·벡터DB·UI·배포 대안 동시 존재 | 하나의 작은 경로만 선택, 전체 설치 안 함 |

초기 후보는 LangGraph·Ollama·FastAPI/Vue·로컬 검색·Git/Docker·기능/보안 도구다. 구체 선정 기준은 [구현 계획](delivery.md)에 둔다. **추가 100개 수집은 현재 필요하지 않다.** 다음으로 필요한 자료는 더 많은 링크가 아니라 실제 배포 환경 정보·무료 공급자 자격·허용 코퍼스·작은 완주 명세다.

## 6. 공식 자료와 현재 판단

계정별 자격·실호출·청구 내역은 조회하지 않았다. 아래는 확인일의 공개 문서이며 구현 시 재확인한다.

| 자료 | 확인 사실·채택 범위 |
|---|---|
| [Ollama 가격](https://ollama.com/pricing) | 무료 플랜에도 대상·사용량 제한이 있다. 무제한 무료 API로 간주 안 함 |
| [Alibaba Model Studio 무료 한도](https://www.alibabacloud.com/help/en/model-studio/new-free-quota) | 자격·리전·대상 모델·유효기간·Free Quota Only 확인 필요. 계정 미검증 |
| [DeepSeek 공식 API 가격](https://api-docs.deepseek.com/quick_start/pricing/) | 토큰별 과금. 공개 가중치·무료 웹 채팅은 무료 API의 증거가 아님 |
| [Qwen Code 인증](https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/auth.md) | 과거 OAuth 무료 tier는 2026-04-15 중단 명시. 과거 일일 무료 호출 수 적용 안 함 |
| [Jev/TypeSafe 소개](https://docs.typesafe.ai/introduction) | 타입 있는 판단 API 설명. 무료 로컬 가중치 제공·현재 무료 API 자격은 미확인 |
| [Qwen3 8B Ollama](https://ollama.com/library/qwen3:8b), [Qwen3.5 4B](https://ollama.com/library/qwen3.5:4b) | 로컬 후보 존재. 파일 크기는 실행 메모리·성능 보증 아님 |
| [DeepSeek-R1](https://github.com/deepseek-ai/DeepSeek-R1) | 공개 모델·증류 후보의 출처. 실제 사용할 작은 체크포인트·라이선스 별도 고정 |
| [Qwen3-Embedding 0.6B](https://ollama.com/library/qwen3-embedding:0.6b) | 허용 계열 로컬 임베딩 후보. 생성 모델과 동시 상주 미확인 |
| [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | durable checkpointer·thread ID·재개 의미·부작용 중복 위험 확인 |
| [Ollama FAQ](https://docs.ollama.com/faq) | 병렬 요청/문맥의 메모리·Mac 실행 제약 참고. Mac 호스트 서빙과 컨테이너 실행 분리 |

유료 OpenAI Sol/Astra 기본안은 철회 상태다. 사용자 보유 키의 모델·무료 잔액을 추측하지 않고 어떤 API도 호출하지 않았다. “보안 이슈 없는 최고의 모델”은 보증할 수 없어 공급망·데이터 흐름·권한과 품질 확인으로 대체했다.

## 7. 스킬 활용과 실제 산출물

| 스킬 | 적용 |
|---|---|
| ECC intent-driven-development | 확정 조건/가정 분리, AC별 상황·행동·기대·금지·확인 방법 |
| ECC product-capability | 생명주기·불변식·신뢰 경계·열린 결정·구현 인계 |
| ECC contract-first | 명령·이벤트·스냅샷 JSON Schema를 단일 필드 원본으로 구성 |
| ECC context-and-decisions / strategic-compact | 안정된 조건·최신 명세·원문 보존·구조화 인수인계. 작업 현황과 도메인 용어 혼합 방지 |
| ECC loop-design-check | 기계적으로 확인 가능한 종료 조건·독립 판정 참고. 횟수 상한 권고는 사용자 지시로 제외 |
| ECC docs-governance | 문서별 소유 사실과 단일 진입점. 불필요한 병렬 관리 체계 만들지 않음 |
| PDF | 실제 평가·제출 페이지와 Validator 설계 재대조 |
| frontend-design | 업무에 맞는 구체적 시각 방향·위계·상태·접근성 |
| ponytail | 한 템플릿·최소 실행 구조·기존 패턴 참고·불필요한 200개 설치 방지 |

blueprint와 ADR 스킬도 지침을 확인했지만 전체 절차를 수행했다고 주장하지 않는다. 현재는 서브 검토·GitHub 작업 없이 문서로 대조했고, 별도의 승인된 ADR 체계를 새로 도입하지 않았다. 이미 요청된 기획 문서의 선택 이유는 아키텍처에서 관리한다.

## 8. 확인 한계와 착수 판단

기획·수용 기준·계약·화면·작업 순서를 작성했다. 앱 구현·모델 다운로드/실행·200개 저장소 감사·API 자격/청구 확인·새 UI 브라우저 검수·배포는 미실시다. 작은 로컬 모델의 코딩 품질, 무료 LIVE 가용성, 실제 배포/평가 환경이 주요 남은 위험이다.

문서만으로 모든 구현 준비가 끝난 것은 아니다. 다음 작업은 [D0 환경 확인](delivery.md)이며, 확인된 한 경로로 첫 실제 완주를 구현한다. 기능 검증과 보안은 이후 실제 실행 근거로 갱신한다.

작성 후 문서 대조 결과: 요구사항 27개에 수용 시나리오 24개를 연결했고 누락된 AC 참조는 없었다. Markdown 문서 9개의 로컬 링크 26개는 대상 파일이 존재했다. 프로토콜은 JSON 파싱·내부 참조 66개·정의 20개의 참조 연결과 JSON Schema 2020-12 메타 스키마 형식을 확인했다. 이 확인은 문서 구조에 한정되며 API 구현·상태 전이·실제 보안의 통과 증거가 아니다.
