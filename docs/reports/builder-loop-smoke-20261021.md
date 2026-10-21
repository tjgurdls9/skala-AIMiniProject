# 빌더 루프 형식 스모크 (개발 확인 · 수용 아님)

2026-10-21. `infra/dev_checks/smoke_builder_loop.py`, 모델 `qwen3.5:4b`(Q4_K_M, 추론 슬롯 1), 실제 Docker(python/node digest 고정 이미지), 임시 작업 공간·DB. 모델이 만든 결과를 자율 개발 성과로 세지 않으며 수용 판정이 아니다. 작업 세션이 작업(backend 1개)을 하네스에서 직접 주었고 기획·승인 단계는 거치지 않았다. S09 DB, worker 운영 경로, 카공지도·문의 앱은 쓰지 않았다.

입력(범용 초소형): "두 정수를 더하는 함수 add(a, b)를 제공한다", AC "add(2, 3)이 5를 반환한다". 프롬프트에 정답·힌트를 넣지 않았다(환경 사실 한 줄만 지침에 추가: 컨테이너는 네트워크가 없고 파이썬 이미지에는 표준 라이브러리만 있다).
상한: 모델 호출 40회 또는 20분. 실제 사용: 4회, 27.8초.

## 결과

| 항목 | 값 |
|---|---|
| 종료 사유 | model/runtime failure: JSONDecodeError Unterminated string starting at: line 6 column 24 (char 177) |
| 모델 호출 | 4회 (호출당 약 7초) |
| 동작 JSON 형식 준수(스키마 통과) | 3/4 — 나머지 1회는 JSON 자체를 해석할 수 없어 루프가 중단됨 |
| 거부·형식 오류(관찰로 되돌린 것) | 0건 (도구 호출 3건 중 거부 0건) |
| RED 도달 | 아니오 (run_tests를 한 번도 호출하지 않음) |
| GREEN 도달 | 아니오 |
| 만든 파일 | test_add.py |

## 모델 호출과 서버 기록

| # | 게이트 | 스키마 통과 | 시간 | 입력 바이트 | 동작 |
|---|---|---|---|---|---|
| 1 | red | 예 | 6.9s | 2357 | `{"tool": "write_file", "args": {"path": "test_add.py", "content": "def test_add_returns_sum():\n    assert add(2, 3) == 5\n", "expected_digest": null}` |
| 2 | red | 예 | 6.6s | 2731 | `{"tool": "write_file", "args": {"path": "test_add.py", "content": "def test_add_returns_sum():\n    assert add(2, 3) == 5\n", "expected_digest": "sha2` |
| 3 | red | 예 | 7.1s | 2847 | `{"tool": "write_file", "args": {"path": "test_add.py", "content": "def test_add():\n    assert False, \"Implementation not yet complete\"", "expected_` |
| 4 | - | JSON 해석 실패 | 7.1s | - | `"JSONDecodeError"` |

도구 원장:

| seq | 도구 | 인자 | 결과 | 종료 코드 |
|---|---|---|---|---|
| 1 | write_file | `{"content_bytes": 54, "expected_digest": null, "path": "test_add.py"}` | 허용 | None |
| 2 | write_file | `{"content_bytes": 54, "expected_digest": "sha256:dd6b4fb07ec5aac6af5dd4345230ece27c0d41f19bd96cd3ab03424b881eb` | 허용 | None |
| 3 | write_file | `{"content_bytes": 67, "expected_digest": "sha256:dd6b4fb07ec5aac6af5dd4345230ece27c0d41f19bd96cd3ab03424b881eb` | 허용 | None |

## 막힌 지점

1. **모델 출력 해석 실패가 루프를 끝낸다.** 4번째 호출의 응답이 `JSONDecodeError`(unterminated string)였고, 현재 루프는 `worker.infer` 예외를 잡지 않아 실행이 실패로 끝난다. 원인(문자열 안 개행 등)은 이 하네스가 원문을 남기지 않아 확인하지 못했다.
2. **다음 단계를 모르는 반복.** 테스트 파일을 쓴 뒤 `run_tests`로 넘어가지 않고 같은 파일을 두 번 더 썼다(2번은 같은 내용, 3번은 `assert False`로 바꿈). 모두 형식은 맞고 서버는 정상 기록했지만 RED로 가는 동작을 하지 못했다. 3번째의 `assert False`는 RED를 만들려는 형식적 시도로 보이며, 이 게이트는 그런 테스트도 서버 입장에서는 실제 실패 종료 코드로 받아들일 수 있다(독립 검증이 걸러야 할 한계).
3. 호출당 입력은 작았다(예산 14000바이트 안). 크기가 아니라 동작 선택이 문제로 보이나, 4번의 표본으로 일반화할 수 없다.

## 설계 변경 제안 (아직 적용하지 않음)

- 모델 출력 해석 실패·스키마 위반을 루프가 관찰("출력이 올바른 JSON이 아님")로 되돌리고 반복 감지에 포함한다. 해석 실패 원문(앞 N바이트)은 원장에 남긴다.
- 서버가 원장 상태로 계산한 "다음에 해야 할 도구"를 gate.next에 구체적으로 적는다(예: 테스트를 썼으나 아직 실행하지 않았음 → `run_tests`). 정답이 아니라 서버가 아는 진행 상태의 표현이다.
- 내용이 같은 파일을 다시 쓰는 동작은 진전 없음으로 보고 연속 2회에서 멈춘다.
- `Ollama.generate`의 시스템 프롬프트가 "Never ... execute tools"라고 말한다. 빌더 루프에서는 모델이 도구 호출을 제안하는 역할이라 혼동 가능성이 있어 역할별 시스템 프롬프트가 필요하다(효과는 미확인).
- 이 표본(4회)은 모델이 JSON 동작 형식 자체는 따르나 TDD 순서를 스스로 밟는지는 확인하지 못했다. 위 수정 뒤 같은 소형 작업으로 다시 한 번 확인해 보는 것이 순서다.

---

# 2차 확인: 루프 견고화 이후 서로 다른 초소형 작업 2개 (개발 확인 · 수용 아님)

적용한 수정(`c2890d5`): 해석 불가 출력을 관찰로 되돌리고 원장에 남김, 같은 내용 재작성은 "변경 없음" 관찰, gate.next를 원장 사실+규칙으로 표현, 역할별 시스템 프롬프트. 같은 조건(qwen3.5:4b, 슬롯 1, 실제 Docker, 임시 작업 공간, 작업당 40회/20분 상한, 정답·힌트 없음)에서 두 작업을 각각 1회 실행했다. 작업 세션이 하네스에서 작업을 직접 주었고 기획·승인은 없다.

| 작업 | 호출 / 시간 | 스키마 통과 | 도구 실행(원장) | 관찰 오류 | RED | GREEN | 종료 |
|---|---|---|---|---|---|---|---|
| (a) Python: add(a, b) | 40회 / 228.8초 | 40/40 | 0건 | 39건 | 아니오 | 아니오 | stopped by the call/time limit |
| (b) Node: reverse(s) + node --test | 4회 / 16.4초 | 4/4 | 0건 | 3건 | 아니오 | 아니오 | stopped for the user: INVALID_COMMAND 같은 동작과 결과가 3번 반복돼 사람의 입력이 필요합니다: |

- (a) Python: add(a, b): 가장 자주 낸 동작 [('{"tool": "finish", "summary": "The task requires implementin', 20), ('{"tool": "list_files", "args": {"path": "."}}', 20)]; 관찰 오류 예: ['아직 끝낼 수 없습니다: 아무 변경 없이 작업을 끝낼 수 없습니다. 파일을 작성하세요.', "인자 형식 오류: ToolBox.list_files() got an unexpected keyword argument 'path'"]
- (b) Node: reverse(s) + node --test: 가장 자주 낸 동작 [('{"tool": "list_files", "args": {"path": "."}}', 3), ('{"tool": "finish", "summary": "No test files exist in the re', 1)]; 관찰 오류 예: ['아직 끝낼 수 없습니다: 아무 변경 없이 작업을 끝낼 수 없습니다. 파일을 작성하세요.', "인자 형식 오류: ToolBox.list_files() got an unexpected keyword argument 'path'"]

## 관찰

1. **JSON 형식 준수는 100%지만 실행된 도구 호출이 0건이다.** 두 작업 모두 모델은 항상 스키마를 통과하는 동작을 냈으나, 첫 동작으로 `finish`(작업 요약 서술)를 고르거나 인자가 틀린 `list_files(path=".")`를 반복했다. `list_files`는 인자를 받지 않는다. 지침의 텍스트 도구 목록만으로는 4B가 인자 형식을 지키지 못했다.
2. **(a)에서 두 동작을 번갈아 내는 방식이 연속 반복 규칙을 피해 40회를 모두 소진했다**(finish ↔ list_files, 228.8초). 이는 루프의 결함이라 즉시 고쳤다: 기록된 변경이 없는 최근 8단계 안에서 같은 동작·결과가 3번 나오면 멈춘다(`runner/builder_loop.py`, 테스트 추가). (b)는 연속 3회 규칙으로 4번째 호출에서 멈췄다.
3. 모델은 `finish`를 거절당한 이유를 읽고도(서술 요약에 "gate가 RED이며 테스트가 없다"고 쓰면서) `write_file`로 넘어가지 못했다. 상태를 이해해도 다음 동작을 고르는 데 실패한다. 서버는 정상 기록·거부했고 RED/GREEN을 잘못 인정하지 않았다.

## 설계 변경 제안 (승인 대기, 적용 안 함)

1. **도구별 인자 스키마를 동작 스키마에 넣는다.** `ACTION_SCHEMA`를 도구마다 `{tool: const, args: {필수·허용 속성}}`인 `anyOf`로 바꿔 Ollama의 구조화 출력이 인자 이름까지 강제하게 한다. 인자를 받지 않는 도구에 `path`를 넣는 형식 오류가 생성 단계에서 사라진다(Ollama가 anyOf를 문법으로 지원하는지는 미확인, 확인 필요).
2. **서버 상태로 동작 스키마를 좁힌다.** 원장상 `finish`가 허용되지 않으면 스키마에서 `finish`를 뺀다. 그러면 모델이 서술로 도망갈 수 없다. 정답이 아니라 게이트 규칙의 문법화다.
3. **지침을 줄이고 도구별 형식 예시(자리표시자만)를 넣는다.** 언어·작업 중립 예시(`{"tool":"write_file","args":{"path":"<path>","content":"<text>"}}`)는 설계 문서의 허용 범위다.
4. 위 1–2를 적용한 뒤 같은 두 작업으로 다시 확인한다. 그래도 도구가 실행되지 않으면 qwen3.5:4b로는 이 루프 형식을 따르기 어렵다는 결론이고, 호출당 동작 수를 줄이거나(예: 한 호출에 파일 하나의 전체 내용만 요청하는 기존 패치 방식과의 혼합) 모델 후보 재평가를 설계 항목으로 올려야 한다.

