<!-- 출처: 독립 리뷰 서브 에이전트(ecc:code-reviewer, sonnet, 추론 강도 high) 1개의 최종 보고 원문. 사용자 결정(관제 전달)에 따라 실행.
     리뷰 대상: git diff 6cc9a0b..d849722 -- backend runner infra (work/codex-runtime). 읽기 전용, 코드·Docker·Ollama·테스트 미실행.
     아래 본문은 수정 없이 그대로 보존했다. 이 파일은 개발 세션의 독립 리뷰 기록이며 제품의 검증·보안 판정이 아니다.
     원문 보존 이후 런타임 세션이 확인한 것: H-1(runner/plan_extras.py:120 prefix, runner/check_runner.py:80 by_id), H-2(infra/checks/security.py:31 vendor),
     L-5(backend/api.py:134, backend/README.md:3, runner/release.py:117), L-7(runner/workspace.py:29, runner/tdd_gate.py:18 full_match, 이 장비 Python 3.14.7)는
     해당 줄이 보고와 같음을 읽어서 확인했다. 나머지는 확인하지 않았고 수정도 하지 않았다. -->

# 코드 리뷰 F0–F6

범위: `git diff 6cc9a0b..HEAD -- backend runner infra`, 읽기 전용. 서버, Docker, Ollama, 테스트 스위트는 실행하지 않았다. 아래 항목은 모두 호출 경로를 끝까지 읽어 확인했다. 확인하지 못한 부분은 PLAUSIBLE로 표시했다.

## 요약

| 심각도 | 건수 |
|---|---|
| CRITICAL | 0 |
| HIGH | 5 |
| MEDIUM | 7 |
| LOW | 8 |

**총평.** 사용자 승인 경로는 견고하다. API 호출자, 모델, 생성 앱이 plan/acceptance 승인을 만들거나 재사용하거나 `met`으로 바꾸는 경로는 찾지 못했다. 컨테이너 격리를 벗어나는 경로도 찾지 못했고, 비밀이 모델 입력이나 아티팩트로 새는 경로도 찾지 못했다. 다만 판정 신뢰성을 깨는 결함이 HIGH 5건 나왔다.

- **판정 위조 2건**
  - 계획자가 정한 AC id 때문에 서로 다른 check가 같은 id를 갖게 되면, 실패한 AC가 `met`이 된다 (H-1).
  - 생성 앱이 `vendor/` 디렉터리 하나로 보안 정적 검사를 통째로 피한다 (H-2).
- **RED→GREEN 게이트**: 형식상 통과가 가능하고 `run_command` 우회로가 있다 (H-3).
- **워커**: 도구 실행이 이벤트 루프를 막아 실제 워커 프로세스에서 lease를 잃는다 (H-4).
- **호스트 메모리**: 샌드박스 출력이 호스트 메모리에 전부 버퍼링된다 (H-5).

CRITICAL은 없다. 그러나 H-1, H-2, H-3은 C6(독립 리뷰 후 CRITICAL/HIGH 잔존 0)을 충족하기 전에 닫아야 한다.

## CRITICAL

없음.

## HIGH

### H-1. check id 충돌로 실패한 AC가 `met`이 된다
- 위치: `runner/plan_extras.py:120`, `runner/check_runner.py:80-86`, `runner/review.py:36-47`
- 상태: CONFIRMED
- 설명: check id는 `f"{prefix}-{n}"`로 만들고, `prefix`는 AC id의 `[^A-Za-z0-9_-]`를 `_`로 바꾼 뒤 30자로 자른 값이다.
  - `check_verification`은 AC마다 따로 호출되어 임시 id `c1…`만 본다.
  - `worker.finish`와 PlanView 스키마에는 `verification[].id`의 전체 유일성 검사가 없다.
  - `acceptance_verdicts`는 `by_id = {o.id: o}`로 outcome을 id로 모으므로 마지막 outcome이 앞의 것을 덮어쓴다.
- 시나리오:
  1. 계획자가 AC id를 `"검색"`, `"추천"`처럼 비ASCII로 냈다. 둘 다 `"__"`가 되어 check id가 모두 `__-1`이다. `"AC 1"`과 `"AC_1"`, 또는 앞 30자가 같은 긴 id도 같은 결과다.
  2. AC1의 check는 실패하고 AC2의 check는 통과한다.
  3. `by_id["__-1"]`은 AC2의 outcome이므로 AC1도 `met`이 된다.
  4. 검증자의 판정은 `pass`가 되고 프리뷰와 acceptance 요청까지 진행한다.
  - 의도한 공격자가 아니어도 한국어 id를 쓰는 계획자라면 우연히 발생한다. 사용자는 승인 화면에서 id 충돌을 알아볼 수 없다.
- 수정: check id를 AC 인덱스로 만든다(`f"a{i}-c{n}"`). `worker.finish`에서 `verification` id 전체의 유일성을 검사한다(AC id 유일성 검사와 같은 위치). `acceptance_verdicts`는 중복 id를 `error`로 처리한다.

### H-2. `vendor` 디렉터리 하나로 보안 정적 검사를 전부 우회한다
- 위치: `infra/checks/security.py:31` (`if "vendor" in path.parts: continue`)
- 상태: CONFIRMED
- 설명: 이 줄은 `read_text()`와 secret, AST, JS 검사보다 앞에 있다. 후보 안 어느 경로든 `vendor` 디렉터리 아래 파일은 `dynamic_execution`, `unsupported_import`, `secret_format`, `unsafe_browser_code` 검사를 받지 않는다.
- 시나리오:
  1. 모델이 `server/vendor/helper.py`에 `eval`, `os.system`, 비밀 형식 문자열을 넣는다.
  2. 앱 본체가 그것을 import한다. `local` 허용 집합에는 `p.stem`과 `p.parent.name`이 있어 `vendor` 이름도 허용된다.
  3. `static`과 `secrets`가 true가 되고, grype에 취약점이 없으면 보안 보고서가 `pass`다.
  - 테스트(`grep vendor backend/tests`)도 이 경로를 다루지 않는다.
  - model-authored 모드에서는 `allowed_imports`가 stdlib 전체라 `subprocess`, `ctypes`, `importlib`도 걸리지 않는다. `from os import system as s`처럼 별칭을 써도 `getattr(node.func, "attr")` 이름 검사를 피한다. 정적 검사 전체가 얕은 방어선이다.
- 수정: `vendor` 면제를 제거한다. 후보 제어 입력으로 면제 여부를 정하지 않는다. 제3자 코드는 승인된 의존성 경로로만 들어오게 한다. 보고서에 보안 검사의 한계를 명시한다.

### H-3. RED→GREEN 게이트를 형식적으로 통과할 수 있고, `run_command`가 우회로다
- 위치: `runner/tools.py:107-112`, `:119-128`; `runner/commands.py:60-66`; `runner/tdd_gate.py:57-73`
- 상태: CONFIRMED (코드 경로 기준. 실행 재현은 하지 않았다)
- 설명 (a): `validate_test_command`는 argv 앞 세 토큰만 본다. 서버가 쓰는 판정 근거는 "test 경로 파일 write + `run_tests` 실패 + 비test 파일 write + `run_tests` 성공" 뿐이다. `run_tests`가 테스트를 실제로 실행했는지는 보지 않는다.
- 시나리오 (a):
  1. `write_file tests/x.txt`를 호출한다. 패턴 `tests/**`에 맞아 `tests_written`이 된다.
  2. `run_tests ["python","-m","unittest","no_such"]`가 exit 1이라 RED가 된다.
  3. `write_file main.py`로 아무 내용을 쓴다.
  4. `run_tests ["python","-m","unittest","-h"]`는 exit 0이라 `phase=done`이다.
  5. `can_finish`가 true가 되어 task가 끝난다.
  - 같은 방식으로 `node --test`에 테스트가 0개여도 exit 0이다. 모델 비교 보고서(6995dfa)가 이미 "형식상 GREEN"을 기록했는데, 서버 게이트에는 대응이 없다.
- 설명 (b): `_mutate`의 구현 파일 잠금(RED 전 쓰기 거부)과 `write_scope` 강제는 `write_file`, `delete_file`, `move_file`에만 걸려 있다. `run_command`는 `/work`가 RW로 마운트된 컨테이너에서 임의 python/node를 실행한다.
  - `python -c "open('app.py','w').write(...)"`로 RED 전에 구현 파일을 쓸 수 있다.
  - 같은 방법으로 쓰기 범위 밖에도 쓸 수 있다.
  - `unledgered`는 task에 명령이 한 번이라도 있으면 `[]`를 반환한다(`runner/intervention.py:15`). 그래서 개입 표시도 남지 않는다.
- 영향: 판정 위조는 아니다. 최종 판정은 승인된 check를 쓰는 독립 검증자가 내린다. 그러나 "서비스가 RED/GREEN 순서를 강제한다"(설계 §4.4, F3)는 보장이 성립하지 않는다.
- 수정: GREEN 판정에 테스트가 실제로 1개 이상 실행됐다는 근거를 요구한다. 예를 들어 runner 출력의 "Ran N tests"나 pass 수를 파싱하고, `-h`, `--help`, `--version` 같은 플래그는 거부한다. 구현 잠금은 `run_command` 전후 작업 공간 스냅샷 비교로 확장하거나, RED 전에는 `run_command`를 읽기 전용 도구로 제한한다.

### H-4. 도구 실행이 이벤트 루프를 막아 워커가 자기 lease를 잃는다
- 위치: `runner/builder_loop.py:220`, `runner/tools.py:133`, `runner/commands.py:115`, `runner/worker.py:55-67`, `:311-322`, `runner/pipeline.py:110-112`
- 상태: CONFIRMED
- 설명: `BuilderLoop.run`은 async인데 `self.execute(...)`를 동기 호출한다. 이 호출은 `subprocess.run(..., timeout≤300)`로 Docker를 직접 기다린다. 이때 `keep_alive`는 루프가 비어야 실행되는데 막혀 있다. lease는 10초이고 갱신 주기는 2초다.
- 시나리오:
  1. `install_dependencies`나 느린 `npm test`가 약 10초를 넘긴다.
  2. 호출이 끝나고 `heartbeat()`가 돌면, 자기 소유지만 만료된 lock(`lock[1] <= clock`)이 "인수" 분기를 탄다.
  3. 실행 중 job을 모두 `pending`으로 되돌리고 attempt를 `superseded`로 기록한다.
  4. 다음 `worker.infer`에서 `ModelUnavailable("Attempt superseded")`가 발생한다.
  5. 같은 job이 새 attempt로 재claim된다. 모델 추론과 명령 하나가 매번 낭비되고 진행이 매우 느려진다.
- 테스트가 놓친 이유:
  - 테스트는 `heartbeat()`를 수동 호출한다.
  - 스모크 하네스(`infra/dev_checks/smoke_builder_loop.py`)는 자체 `Metered` 어댑터를 쓴다. 실제 `Worker.run`의 keep_alive 루프를 거치지 않는다.
  - `read_tree`도 `build`에서 동기 호출된다(`runner/pipeline.py:110,112`).
- 수정: `await asyncio.to_thread(self.execute, ...)`로 바꾸고, `context()`의 DB와 파일 접근과 `read_tree`도 `to_thread`로 감싼다. 같은 프로세스 안의 자기 lease 만료는 인수가 아니라 갱신으로 처리한다.

### H-5. 샌드박스 출력과 파일 크기에 호스트 측 상한이 없다 (메모리, 디스크)
- 위치: `runner/commands.py:115,121-124`, `runner/review.py:74`, `runner/workspace.py:61-63,130-133`, `runner/pipeline.py:78-87`, `runner/candidate.py:136`
- 상태: CONFIRMED (코드 기준. 실제 메모리 한계는 실행으로 확인하지 못했다)
- 설명: `subprocess.run(capture_output=True)`는 컨테이너 stdout/stderr 전체를 워커 메모리에 모은 뒤에야 `[:65536]`로 자른다.
  - 모델이 `timeout`을 최대 300초로 줄 수 있다.
  - 컨테이너의 `--memory 512m`은 호스트 파이썬 프로세스의 버퍼에 영향을 주지 못한다.
  - 검증자의 `command` check 실행(`CandidateEnv.run`)도 같다.
  - `list_files`가 파일마다 `_safe_digest`를 부르는데, `_text`는 크기 검사 없이 `path.read_text()`로 통째로 읽는다. `read_tree`와 `manifest`도 전체를 읽는다.
  - `/work`에는 디스크 쿼터가 없다.
- 시나리오: 모델이 만든 코드가 `while True: print(...)`를 60초 돌려 수 GB를 출력한다(실제 로그에 있는 무한 출력 버그와 같은 종류). 또는 run_command가 수 GB 파일을 /work에 쓰면 이후 `list_files`가 매 단계 그 파일을 메모리에 올린다.
  - 결과는 워커 OOM, 호스트 스왑 폭주, 디스크 충만이다.
  - 이 장비는 16GB 멈춤 사건(`docs/reports/memory-incident-20261021.md`)을 이미 겪었고, memory_guard는 `infra/dev_checks` 개발용이다. 서비스 경로에는 없다.
- 수정: 출력을 `Popen`으로 읽으며 상한(예: 64KB 이상이면 읽기를 멈추고 컨테이너를 kill)을 둔다. `_text`와 `list_files`는 `stat().st_size`를 먼저 보고, `manifest`는 청크로 해시한다. `/work` 쓰기 상한(tmpfs나 쿼터)도 둔다.

## MEDIUM

### M-1. 재시도한 task가 거짓 개입으로 표시되고, 탐지에는 사각지대가 있다
- 위치: `runner/pipeline.py:95-102`, `runner/intervention.py:12-17`
- 상태: CONFIRMED
- 설명: `edits_between_tasks`는 "이전 task 커밋 뒤의 변경은 모두 개입"이라고 본다. 같은 task를 다시 시도할 때(pause/resume, 워커 재시작, H-4의 lease 상실) 첫 시도에서 모델이 도구로 쓴 미커밋 파일이 `dirty`에 잡힌다.
- 시나리오: task 2를 진행하다 pause했다가 resume하면 `code_diff.interventions=[edited_between_tasks]`가 붙는다. 이 run은 "자율 완주 근거 아님"(R30)이 되어 평가가 오염된다.
- 반대 방향의 사각지대:
  - 첫 task는 `last`가 없어 `[]`를 반환한다. 시작 전에 사람이 작업 공간에 파일을 넣어도 `before`와 `after`가 같아 `changes`에 안 잡히고 그대로 커밋된다. `Sandbox.workspace`는 이미 있는 디렉터리가 비었는지 검사하지 않는다.
  - 명령이 한 번이라도 있던 task의 변경은 귀속하지 못한다(`unledgered`의 알려진 한계).
- 수정: `inherited`를 계산할 때 해당 task의 원장에 기록된 쓰기 경로는 제외한다. 첫 task는 시작 시 작업 공간이 비어 있거나 원장 경로와 일치하는지 검사한다.

### M-2. 모델 도구 grant 유효 시간 900초가 task 소요 시간보다 짧을 수 있다
- 위치: `runner/access.py:17`, `runner/tools.py:57`, `runner/builder_loop.py:170-173`
- 상태: CONFIRMED (조건: 한 attempt가 15분을 넘길 때)
- 설명: grant는 `time.time() + 900`이다. 만료 후 `_call`이 `self.authority()`에서 `DomainError("FORBIDDEN", ...)`를 던진다. 이 예외는 `try` 밖이라 원장에도 남지 않는다. `BuilderLoop.execute`는 FORBIDDEN을 재전파 대상으로 보지 않아 모델에게 도구 오류 관찰로 돌려준다.
- 시나리오: 모델이 같은 도구를 3번 반복하면 `STREAK_LIMIT`에 걸려 "같은 동작 반복" `needs_input`이 된다. 실제 원인(권한 만료)이 사용자에게 보이지 않는다. 기록상 think=True 40회는 608초였고, 파일이 여러 개인 task는 15분을 넘기기 쉽다.
- 수정: 만료를 `RUNTIME_UNAVAILABLE`로 분류해 `waiting_resource`로 보내거나 루프 중 grant를 갱신한다.

### M-3. SECRET 정규식이 단어 경계 없이 일치해 정상 텍스트를 막는다
- 위치: `backend/contracts.py:12`, 사용처 `runner/workspace.py:79`, `backend/api.py:115`, `runner/pipeline.py:201`
- 상태: CONFIRMED
- 설명: `sk-[A-Za-z0-9_-]{20,}`에 `\b`가 없다. 실제로 `risk-assessment-calculation.py`, `task-management-service-handler`, `disk-usage-monitoring-report`가 일치한다.
- 영향:
  - 모델이 이런 kebab-case 문자열(CSS 클래스, 슬러그, 파일명)을 `write_file`에 쓰면 INVALID_COMMAND로 거부된다.
  - 사용자 요청도 `payload()`에서 "비밀정보를 요청에 넣지 마세요"로 거부된다.
  - 가장 나쁜 것은 `pipeline.py:201`이다. `require`가 try/except 바깥에 있어, 보고서 본문(보안 findings 경로, grype 보고서, check `detail`)에 일치 문자열이 있으면 `DomainError`가 `review()` 밖으로 나가 `needs_input`이 된다. 보고서가 저장되지 않으므로 resume하면 같은 후보에서 같은 오류가 반복된다.
- 수정: `(?<![A-Za-z0-9])sk-…`처럼 경계를 둔다. 보고서의 SECRET 검사 실패는 `error` 판정으로 저장해 같은 후보에서의 무한 반복을 끊는다.

### M-4. 검증자 판정이 앱 기동 실패(`healthy=False`)를 반영하지 않는다
- 위치: `runner/review.py:35-47`
- 상태: CONFIRMED
- 설명: `healthy=False`는 `summary`와 `tools.healthy`에만 들어간다. 판정에는 http check가 있을 때만 failed로 반영되고, 없으면 영향이 없다.
- 시나리오: 계획의 check가 file이나 command뿐이고 앱 서버가 뜨지 않는다. 검증자는 `pass`를 낸다. 이어 `Pipeline.release`의 상태 확인이 `ModelUnavailable("Preview health unavailable")`로 실패하고, `failure_reason`이 이를 `waiting_resource`로 분류한다. 사용자는 "모델 또는 자원을 확인하라"는 오도된 안내를 받고, resume해도 같은 결과가 반복된다.
- 수정: 정상 응답하지 않으면 verdict를 `fail`로 한다. 앱 선언이 있는 후보는 health를 기본 check로 포함한다.

### M-5. 보안 스캐너가 비UTF-8 파일에서 죽고, 번들 파일에는 오탐한다
- 위치: `infra/checks/security.py:33`, `:56-57`
- 상태: 크래시는 CONFIRMED, 번들 오탐은 PLAUSIBLE
- 설명:
  - `path.read_text()`가 후보 안 모든 파일에 무방비로 호출된다. `git add -A`가 `run_command` 산출물(이미지, DB 파일)도 커밋하므로 비UTF-8 파일이 후보에 들어올 수 있다.
  - 이 경우 스크립트가 크래시하고 `docker run`이 비정상 종료하며 `ModelUnavailable`이 된다. 리뷰는 `error`가 되어 `waiting_resource`가 되고, 사용자 입장에서는 자원 문제처럼 보인다.
  - 별개로 `.js`/`.html`의 `innerHTML|eval(|https?://`는 Vue 번들(`dist/*.js`)이나 `xmlns="http://www.w3.org/..."`에서 오탐 `fail`을 낼 수 있다.
- 수정: 바이너리와 인코딩 오류는 파일 단위 finding으로 처리하고 스캔을 계속한다. 오탐은 `vendor` 면제가 아닌 다른 방법으로 다룬다.

### M-6. 예기치 못한 예외가 진단 없이 삼켜진다
- 위치: `runner/worker.py:39,274-275`, `runner/pipeline.py:199-200`
- 상태: CONFIRMED
- 설명: 저장소 전체에 `logging`이 없다. `tick`의 `except Exception`은 `failure_reason`으로 넘기고, DomainError 외 예외는 "역할 출력 또는 처리 오류입니다…" 고정 문구만 남는다. 예외 타입도, 메시지도, 트레이스백도 남지 않는다. `review`는 `error_type`만 저장한다. H-4, M-5 같은 결함을 운영 중에 구분하기 어렵다.
- 수정: 예외 타입과 요약을 원장이나 이벤트에 남기고, 서버 측에는 로그로 트레이스백을 남긴다(비밀은 redact).

### M-7. 후보의 `/data` 볼륨을 앱 사용자(65534)가 쓸 수 없을 수 있다
- 위치: `runner/sandbox.py:74-78`, `runner/candidate.py:113-119`
- 상태: PLAUSIBLE (Docker를 실행하지 못해 확인하지 못했다)
- 설명: 이미지에 `/data`가 없고(Dockerfile에 `RUN`이나 chown 없음), named volume은 root 소유 755로 만들어지는 것이 보통이다. builder 지시문(`INSTRUCTIONS`)은 "data는 /data 아래"라고 하는데, 쓰기 가능한지 검증한 흔적이 없다(`infra/verify_candidate_review.py`는 볼륨 목록만 본다).
- 시나리오: SQLite를 /data에 두는 기본 스택 앱이 검증이나 프리뷰에서 쓰기 오류를 낸다.
- 수정: 실제 컨테이너에서 쓰기 테스트를 추가한다. 안 되면 볼륨을 `--user`와 맞는 소유로 초기화하는 서비스 단계를 둔다.

## LOW

- **L-1. `resume_state` 불일치.** `Worker.claim`(`worker.py:98-114`)과 plan 거절(`store.py:381-383`)은 `needs_input`으로 보내면서 `runs.resume_state`를 갱신하지 않는다(`worker.py:180`과 `pipeline.py:230`은 갱신). 이후 `resume`(`store.py:303-306`)은 오래된 값이나 기본값 `planning`으로 갈 수 있다. `claim`의 승인 재검사가 막아서 승인 우회는 아니다. 사용자가 무의미한 재개 루프에 빠질 수 있다. 수정: `needs_input`으로 들어갈 때 항상 `resume_state`를 정한다.
- **L-2. exit 125/126/127을 인프라 오류로 간주한다.** `runner/tools.py:130-136`, `runner/review.py:31,78`. `npm test`가 "jest: not found"(127)를 내거나 앱 command가 127로 끝나는 정상적인 실패가 `RUNTIME_UNAVAILABLE`/`waiting_resource`로 분류된다. 수정: docker CLI 자체 오류와 컨테이너 내부 종료 코드를 구분한다(예: `--cidfile` 또는 inspect의 State).
- **L-3. argv 정책이 부분적이다.** `runner/commands.py:50-52`는 npm 첫 비플래그 인자만 본다. `npm --prefix x install`은 `DENIED_NPM`을 피한다(네트워크 없음이라 영향은 작다). `package_name`은 버전을 떼어 놓고 비교하므로(`commands.py:68-71`) 승인된 계획의 버전 핀이 설치 시 강제되지 않는다. 전이 의존성도 범위 밖이다(D1 허용 범위지만 승인 화면에 표시되지 않음).
- **L-4. 네트워크가 열린 설치 단계 환경.** `runner/tools.py:154-157`은 `pip install` 때 `PYTHONPATH=/deps/py`(`commands.py:105`)가 이전 설치물을 가리킨다. 이전에 설치된 패키지가 stdlib나 `sitecustomize`를 가리면 네트워크가 열린 단계에서 코드가 실행될 이론상 경로다. 네트워크 토폴로지(허용 호스트 3개 프록시)에 의존한다. PLAUSIBLE이며 확인하지 못했다.
- **L-5. 과제/사용자 특정 잔재.**
  - `backend/api.py:134`: Runtime reasons에 "작은 문의 앱 템플릿만 지원합니다"가 남아 있다. 지금은 사실과 다르다.
  - `runner/release.py:117`: `'tjgurdls9/skala-aiminiproject'`가 하드코딩되어 있다.
  - `infra/checks/security.py:13`: fastapi/pydantic 기본 허용 목록(비 model-authored 경로)이 남아 있다. `review.py`는 항상 `--model-authored`로 부르므로 죽은 코드다.
  - `backend/README.md:3`: "작은 문의 CRUD 템플릿" 서술이 남아 있다.
  - `test_task_neutrality` 정규식은 이 문자열들을 잡지 못한다.
- **L-6. 정리 결과를 무시한다.** `runner/review.py:119-125`는 검증용 컨테이너, 네트워크, 볼륨 삭제 실패를 삼킨다. `file` check의 `exists:false`는 64KB를 넘거나 비UTF-8인 존재 파일에서 잘못 통과한다(`Workspace.read`가 NOT_FOUND를 내기 때문, `review.py:84-90`).
- **L-7. Python 버전 불일치.** `PurePosixPath.full_match`(`workspace.py:29`, `tdd_gate.py:18`)는 3.13 이상에서만 있다. README(`backend/README.md`)는 "3.11 이상"이라고 한다. 3.11/3.12에서는 모든 쓰기와 `is_test_path`가 `AttributeError`로 죽는다.
- **L-8. 아직 연결되지 않은 코드.**
  - `backend/external_access.py`: https 출처 확인만 있고 사설/루프백 대상 거부가 없다. 연결할 때 SSRF 방어가 필요하다.
  - `runner/release.py`: 배포 어댑터(`prepare/authorize`)는 API에 연결되어 있지 않다. `decide`가 `plan`/`acceptance` 외 게이트를 거절하므로 release 승인은 현재 만들어질 수 없다. 이 의미에서 안전하지만 미검증 코드다.

## 확인했지만 문제 없던 것

**승인 우회와 재사용**
- `Store.decide`
  - pending 상태와 `target_digest`가 일치해야 한다.
  - `target_digest == digest(target)`이어야 한다.
  - `spec_version_id`가 현재 스냅샷과 같아야 한다.
  - 게이트별 상태 조건(`awaiting_plan_approval` / `preview_ready`)이 필요하다.
  - 저장된 spec의 `plan_digest`와 일치해야 한다.
  - 승인은 `BEGIN IMMEDIATE`로 직렬화되며 `expected_state_version`이 맞아야 한다.
- 오래된 후보 재사용
  - `invalidate_acceptance`가 새 후보 고정(`pipeline.py:157`), 리뷰 재시작 resume(`store.py:315`), `request_changes`에서 호출된다.
  - `check_acceptance_decision`이 최신 후보, 두 pass 보고서, `acceptance_target` 동일성을 다시 요구한다.
  - `AcceptanceTarget`에 `validator_report_digest`가 결속된다.
- 사람 확인 AC
  - `acceptance_verdicts`가 `manual`을 `not_run`으로 둔다.
  - `model_validation_body`가 `manual_pending`을 따로 둔다.
  - `acceptance_status`는 보고서만 읽는다.
  - 사용자 승인이 `met`으로 섞이는 경로는 없다.
- `request_acceptance`는 `any(pending/approved)`로 중복을 막는다.
- `authorize`/`prepare`는 acceptance 승인 id까지 target에 결속한다.

**검증자와 보안 보고서**
- 검증자는 모델을 부르지 않고, `outcome`은 기대값과의 기계 비교다.
- 도구 오류는 `error`이고 통과가 아니며, `not_run`도 통과가 아니다.
- check의 `ac_ids`는 서버가 덮어써서 다른 AC에 연결할 수 없다.
- command check는 인라인 코드만 허용되고 `TEST_WORDS`로 시험 실행기를 거른다.
- 이미지에서 builder 테스트가 빠진다(`_leave_out_tests`).
- `reviews`는 `UNIQUE(run, candidate, role)`이고 불변 트리거가 있다. 검증자와 보안 역할은 서로의 보고서를 볼 수 없다.
- `claim`이 승인 재검사를 한다. 도구 정책 digest 변경, 계약 digest 변경, 지원 공백이 있으면 막는다.

**job과 트랜잭션**
- job의 version이 `state_version`에 결속된다.
- 중첩 트랜잭션은 찾지 못했다. `store.transaction()`은 모두 `with` 밖의 동기 구간이고, db를 받는 보조 함수는 전부 인자 db를 쓴다.
- `record_tool_call`의 19열 INSERT는 열 수가 맞는다.
- 원장 UPDATE/DELETE 불변 트리거가 있다.

**격리**
- 모델 도구
  - `relative_parts`가 절대경로, `..`, `.git`을 막고, 경로의 각 부분에서 심볼릭 링크를 막는다.
  - `sanitize`가 명령 뒤 심볼릭 링크와 특수 파일을 제거한다.
  - `write`는 `expected_digest` CAS, 파일 수 상한, 64KB 상한, secret 거부가 있다.
- 작업 공간 `.git`은 작업 공간 밖(`<workspace>.git`)에 있다. 호스트 git은 `GIT_SAFE`(`hooksPath=/dev/null`, `fsmonitor=false`, `attributesFile=/dev/null`, `GIT_CONFIG_GLOBAL=/dev/null`)로 실행된다. 컨테이너가 훅이나 config를 심을 수 없다.
- argv 전용, `shell=False`, 허용 실행 파일 4개다.
- docker 인자: `--network none`, `--user 65534`, `--read-only`, `--cap-drop ALL`, `no-new-privileges`, pids/memory/swap/cpus 제한, tmpfs `noexec`, `--log-driver none`이다. 검증은 internal 네트워크다. Docker 소켓, 홈, 환경 변수를 컨테이너에 주지 않는다.
- Dockerfile은 `IMAGE` 정규식과 `validate_app_manifest`로 만들어 줄바꿈 주입이 없다. 이미지 빌드는 `--network=none`이다.
- 레지스트리 프록시는 CONNECT를 3개 호스트의 443으로만 허용한다.
- 프리뷰 프록시는 loopback 포트에만 게시하고, CSP, CORS, `frame-ancestors`를 앱이 제거할 수 없다.

**API와 기타**
- API: loopback/Host/Origin 검사, CSRF 토큰, HttpOnly SameSite=Strict 쿠키, 요청 크기 제한, DNS rebinding 방어(`hostname` 검사)가 있다.
- 기록 가져오기는 읽기 전용 replay이고 job이나 grant를 만들지 않는다. 가져온 spec/artifact는 기존 것을 덮어쓰지 않는다.
- `external_access`: SQL 식별자를 정규식으로 검증한다. `private_settings`는 `O_NOFOLLOW`와 권한 600을 확인한다.
- 과제 중립성: `runner/ backend/ infra/ knowledge/`에서 cafemap, kakao, geoapify, map_access, 카공 문자열은 코드에 없다(남은 것은 L-5의 문구 2건).

**한계 (서비스가 풀 수 없는 것)**
- 계획자가 약한 check(예: health만 200)를 AC에 연결해도 서비스는 강도를 평가하지 않는다. 승인 화면에서 사용자가 판단해야 한다.
- 생성 앱이 검증 컨테이너를 알아보고 check에만 맞게 응답하는 것은 구조적으로 막을 수 없다.

## 보지 못한 범위

- 코드, Docker, Ollama, 테스트를 실행하지 않았다. 컨테이너 동작(`/data` 권한, 출력 처리량, exit 코드)은 코드 읽기로만 판단했다.
- `knowledge/` Corpus 구현과 임베딩 경로는 읽지 않았다.
- `backend/tests/*`는 숨겨진 결함 여부만 훑었다(`vendor`, `healthy`, grant TTL 등 특정 항목 위주).
- `infra/dev_checks/*`, `infra/verify_*.py`는 스모크 하네스와 candidate 검증 하네스 일부만 읽었다.
- 레지스트리 네트워크 토폴로지, Docker 데몬 설정, 호스트 파일 시스템 의미(macOS 대소문자 무시)는 확인하지 못했다.
- `frontend/`, `docs/`는 기준 문서(execution-boundary, agentic-foundation-design, contracts, 스키마 일부)만 참조했다.
- Python 3.13 미만 동작은 `full_match` 문서 지식에 근거했고 실행으로 확인하지 않았다.

관련 파일은 모두 `/Users/seohyeokin/workspace/skala-AIMiniProject/.worktrees/codex-runtime/` 아래에 있다. 주요 파일은 `runner/plan_extras.py`, `runner/check_runner.py`, `runner/review.py`, `runner/tools.py`, `runner/tdd_gate.py`, `runner/builder_loop.py`, `runner/worker.py`, `runner/pipeline.py`, `runner/access.py`, `infra/checks/security.py`, `backend/contracts.py`, `backend/store.py`다.

---

# 재검토 (수정분) — 서브 에이전트 보고 원문

<!-- 출처: 재검토 서브 에이전트(ecc:code-reviewer, sonnet, high, 읽기 전용) 1개의 최종 보고 원문. 대상 git diff d849722..2beae84 -- backend runner infra.
     런타임 세션이 확인한 것: N-2는 실제 node:24-slim(digest 91acba91…)에서 `node --test`를 비 TTY로 돌려 확인했다 — 출력은 `ℹ tests 1 / ℹ pass 1`이고 `count_tests`는 None을 돌려준다(CONFIRMED로 승격).
     나머지는 확인하지 않았고, 이 절의 어떤 항목도 아직 고치지 않았다(실서버 실행 중 코드 수정 금지 규칙). -->

범위: `git diff d849722..HEAD -- backend runner infra` (9f4b375, 2beae84). git, grep, 파일 읽기와 로컬 `node -e` 한 줄만 썼다. 테스트, Docker, Ollama는 실행하지 않았다. 아래 CONFIRMED는 "코드 경로를 끝까지 읽어 확인했다"는 뜻이고, 실행 재현은 아니다.

## 요약

| 항목 | 판정 | 남은 틈 |
|---|---|---|
| H-1 check id 충돌 | FIXED | 접두사 재생성 충돌이 이론상 남아 있으나(N-6), 이제 조용히 통과하지 않고 계획 단계에서 거부된다 |
| H-2 vendor 면제 | FIXED | 파일 확장자로 검사 여부를 정하는 얕은 검사는 그대로다(기존 한계) |
| H-3 RED/GREEN, run_command 우회 | FIXED (인용 시나리오 기준) | RED는 테스트 실행 없이도 얻을 수 있다(N-4). node 24 보고 형식에 막힐 수 있다(N-2) |
| H-4 이벤트 루프 | FIXED | 빌더 경로에서 큰 동기 작업은 `build`의 difflib뿐이다(LOW) |
| H-5 출력, 크기 상한 | FIXED | `/deps` 총량과 `Sandbox.docker` 버퍼링은 상한이 없다(LOW). 작업 공간 총량 검사는 사실상 도달 불가다 |
| M-3 SECRET 경계 | PARTIALLY FIXED | `infra/checks/security.py`의 정규식을 안 고쳐 새 문제가 생겼다(N-1). `pipeline.py:203`의 `require`도 그대로다 |

새로 발견한 문제:

| 심각도 | 개수 |
|---|---|
| CRITICAL | 0 |
| HIGH | 2 (CONFIRMED 1, PLAUSIBLE 1) |
| MEDIUM | 2 |
| LOW | 4 |

## 항목별 판정

### H-1 FIXED
- 근거:
  - `runner/plan_extras.py:120-123`은 접두사가 겹치면 `prefix[:24]_{len+1}`로 바꾼다. check id는 `접두사-숫자` 꼴이고 숫자는 순수 숫자라, 마지막 `-`로 나누면 (접두사, n)이 하나로 정해진다. 접두사가 다르면 id도 다르다.
  - `plan_extras.py:127-128`이 만든 전체 목록에 `check_verification`을 한 번 더 돌린다. 이 함수의 `plan_checks.py:80-81`이 중복 id를 오류로 낸다.
  - `runner/worker.py:188-191`의 `finish`가 `extras["verification"]` id 유일성을 검사한다.
  - `runner/check_runner.py:81,89-90`은 id가 반복된 outcome에 연결된 AC를 `unmet / duplicate_check_id`로 만든다. `review.py:40`에서 `"unmet" in states`이면 verdict가 `fail`이다. 예전에 승인돼 DB에 있는 중복 id 명세도 여기서 막힌다.
- 남은 틈: 실패한 check가 다른 AC를 `met`으로 만드는 경로는 찾지 못했다. 생성 접두사 충돌은 N-6에 적었다.

### H-2 FIXED
- 근거: `infra/checks/security.py`에서 `vendor` 건너뛰기를 삭제했다(diff 확인). 파일 루프(23행 이후)에서 남은 건너뛰기는 `.git` 경로뿐이다. `.git`은 `relative_parts`(workspace.py:22)가 쓰기를 금지하고 `git add -A`도 무시하므로 후보에 들어올 수 없다. 심볼릭 링크와 1MB 초과 파일은 건너뛰지 않고 `unsafe_file` finding이 된다.
- 남은 틈 (기존 한계):
  - AST 검사는 `.py`에만 걸린다(34행). 브라우저 코드 검사는 `.js`/`.html`에만 걸린다(54행).
  - `lifecycle.app.json`의 `start`는 `["python","server.txt"]`처럼 확장자 없는 파일도 실행할 수 있다(`validate_command`는 argv[0]만 본다). 그런 파일, `.mjs`, `.cjs`, `.ts`는 비밀 정규식 외에는 검사를 받지 않는다. 이는 H-2 자체가 아니라 "정적 검사는 얕은 방어선"이라는 일반 한계다.

### H-3 FIXED (인용된 시나리오 기준), 잔여 위험 3건
- 근거 (a) GREEN 판정:
  - `runner/tools.py:123-134`에서 `run_tests`가 `count_tests`를 호출한다. exit 0인데 개수가 0이거나 인식 불가이면 원장에 `error_code=NO_TESTS_RAN`을 남긴다.
  - `tdd_gate.py:84-87`은 이 기록을 RED로도 GREEN으로도 세지 않는다. `tdd_gate.py:106-107`은 integration 종류에도 같은 규칙을 적용한다.
  - `commands.py:92-96`의 `NOT_A_RUN`은 `-h`, `--help`, `--version`, `--collect-only` 등을 argv 전체에서 거부한다.
  - 리뷰가 든 `unittest -h`와 테스트 0개 `node --test`는 GREEN에 닿지 못한다.
- 근거 (b) 작업 공간 변경:
  - `commands.py:137`이 `/work`를 `readonly`로 마운트한다.
  - `/deps`는 `deps_writable=True`인 `_install`에서만 쓰기 가능하다(`tools.py:168`). 이 argv는 서버가 만들고 패키지는 허용 목록으로 제한된다.
  - 파일 변경은 `write_file`, `delete_file`, `move_file`로만 가능해서, 명령으로 RED 잠금과 `write_scope`를 우회하던 경로는 막혔다.
  - `intervention.py:13-15`는 이제 명령이 있던 task도 원장 밖 변경을 잡는다.
- 남은 틈:
  1. RED는 여전히 "exit≠0"만 본다. 테스트가 실행되지 않아도 얻을 수 있다(N-4).
  2. `count_tests`는 모델이 통제하는 출력에 속는다. `^Ran N tests?`를 stdout에 찍거나, `@unittest.skip`이 붙은 테스트도 "Ran N"으로 센다. 다만 모델은 `assert True` 테스트를 직접 쓸 수 있으므로, 빌더 게이트에서는 의미 없는 위조다. AC 판정은 독립 검증자가 내린다.
  3. node 24의 보고 형식이 다르면 node 작업이 GREEN에 못 간다(N-2).
  4. 정상 흐름의 부작용 두 가지는 N-3(install 잠금 파일)과 N-5(개발용 점검 스크립트)에 적었다. 읽기 전용 마운트 자체는 `python -m unittest`, `node --test`, `npm test`, `pip install --target /deps/py`, `npm install --prefix /deps`, 두 freeze를 깨지 않는다. 쓰기는 `/deps`나 `HOME=/tmp`(32MB tmpfs)로만 간다.

### H-4 FIXED
- 근거: `builder_loop.py:201`(`context`), `:221`(`execute`), `:223`(`tool_calls`)과 `pipeline.py:112,114,115,116`(`read_tree`, `tool_calls`)을 `asyncio.to_thread`로 옮겼다.
  - `Store.transaction()`은 호출마다 새 sqlite 연결을 연다(`backend/store.py:116-126`). 그래서 `record_tool_call`, `tool_calls`, `RoleScope.authority`는 스레드에서 써도 안전하다.
  - `ToolBox.seen`과 `Workspace`는 순차 await라 한 번에 한 스레드만 만진다. `context`는 `seen`을 건드리지 않는다.
  - 도구가 도는 동안 `keep_alive`의 `heartbeat`가 돌 수 있다.
- 남은 틈 (LOW):
  - `build`는 `pipeline.py:124`의 `difflib.unified_diff`를 쓰기 트랜잭션 안에서 이벤트 루프 위에서 돌린다. 큰 파일 여러 개가 통째로 바뀌면 수 초 막힐 수 있다 (PLAUSIBLE).
  - `heartbeat`의 "내 lock이 만료되면 인수" 분기(`worker.py:55-61`)는 그대로다. 이제 도달하기 어려워졌을 뿐이다.
  - 도구 스레드는 취소되지 않는다. TaskGroup이 취소해도 스레드는 끝까지 돌고 원장에 기록한다(`_record`는 권한을 다시 보지 않는다). 락을 잃어 다른 워커가 같은 task를 이어받으면 이전 시도의 기록이 섞일 수 있다 (PLAUSIBLE, LOW).

### H-5 FIXED
- 근거:
  - `commands.py:32-56`의 `bounded_run`은 스트림당 최대 `CAPTURE_BYTES+1`(262145바이트)만 보관하고 나머지는 읽어서 버린다. 호스트 메모리는 제한된다.
  - 타임아웃이면 `kill()`, `wait()`, `TimeoutExpired`를 낸다. `DockerExecutor.run`(commands.py:152-154)이 `docker rm -f name`으로 컨테이너를 지운다.
  - `finally`에서 리더 스레드를 join(5초)하고 파이프를 닫는다. 리더가 읽는 동안 `wait`하므로 파이프가 가득 차서 막히는 교착은 없다.
  - 좀비도 없다(`wait`가 `kill` 뒤에 있다).
  - `Reviewer.runner` 기본값도 `bounded_run`이다(`review.py:94`). `CandidateEnv.run`은 같은 호출 형식(`stdin`, `capture_output`, `timeout`)을 쓴다.
  - `workspace.py`: `_text`는 크기를 먼저 보고 읽는다(`:149`). `manifest`는 청크 해시이고 결과가 이전 방식과 같다. `read_tree`는 큰 파일을 해시 표식으로 바꾼다. `--ulimit fsize=256MiB`는 파일 하나의 크기를 제한한다.
  - `/work`가 읽기 전용이 되어 컨테이너가 작업 공간 디스크를 채울 수 없다.
- 남은 틈 (LOW):
  - 출력을 많이 내는 컨테이너는 읽고 버리면서 타임아웃(최대 300초)까지 계속 돈다. 리뷰가 제안한 "상한이면 kill"이 아니라 "버리기"를 택했다. 메모리는 안전하지만 CPU는 쓴다.
  - 이미 `/work`가 읽기 전용이라 `MAX_WORKSPACE_BYTES` 검사(`tools.py:143-147`)는 사실상 도달하지 못한다. `write_file`은 최대 200개 × 64KB다. 방어용 코드이고 해롭지 않다.
  - `/deps` 총량은 install 시 상한이 없다(파일당 256MiB만 제한). `Sandbox.docker`(`sandbox.py:25`)는 여전히 `capture_output`으로 전부 버퍼링한다. 다만 출력은 서버가 정한 도구(grype, `security.py`, `http_probe` 읽기 65536 상한)에서 나온다.

### M-3 PARTIALLY FIXED
- 근거: `backend/contracts.py:12`가 `(?<![A-Za-z0-9])sk-…`가 되어 `risk-assessment-calculation`, `task-…` 같은 영문 kebab-case 오탐이 사라진다. 실제 키(`OPENAI_API_KEY=sk-…`, `"sk-proj-…"`, `Bearer sk-…`, 줄 맨 앞)는 앞 글자가 영숫자가 아니라 계속 잡힌다. 영숫자에 바로 붙은 키(`xsk-…`)만 놓친다. 이는 정상 키 형식이 아니다.
- 남은 틈:
  1. `infra/checks/security.py:11`의 비밀 정규식에는 같은 경계가 없다. 새 문제를 만들었다(N-1).
  2. 리뷰가 제안한 둘째 수정은 적용되지 않았다. `pipeline.py:203`의 `require(not SECRET.search(canonical(body)))`는 여전히 try 밖이다. 오탐 범위가 훨씬 좁아졌을 뿐, 걸리면 resume해도 같은 후보에서 같은 오류가 반복되는 구조는 그대로다.
  3. `-sk-…`처럼 앞이 하이픈이나 밑줄인 kebab-case는 여전히 오탐이다(드묾).

## 새로 발견한 문제

### N-1 [HIGH, CONFIRMED] 작성 시 SECRET은 풀리고 보안 정적 검사 정규식은 그대로여서 정상 앱이 늦게 보안 `fail`이 된다
- 위치: `infra/checks/security.py:11`(`sk-[A-Za-z0-9_-]{20,}`, 경계 없음)와 `backend/contracts.py:12`(수정됨)의 불일치.
- 시나리오:
  1. 모델이 할일 앱 HTML이나 CSS에 `task-description-container` 같은 클래스를 쓴다. `sk-` 뒤가 `description-container`(21자)라 `security.py`의 정규식에 일치한다.
  2. 예전에는 `Workspace.write`의 `SECRET` 검사가 작성 시점에 거부했고 모델이 이름을 바꿀 수 있었다. 이제 `write_file`이 통과한다.
  3. 보안 리뷰에서 `secret_format` finding이 나와 `checks.secrets`와 `static`이 false가 된다. `review.py:194`가 `verdict="fail"`을 내고, run이 `needs_input`으로 막힌다.
  4. 빌더에게는 구체적인 피드백이 없다.
- 이전에는 쓰기 검사가 `security.py`의 같은 결함을 가렸다. 이번 수정이 그것을 드러냈다.
- 수정: `security.py:11`을 `(?<![A-Za-z0-9])sk-…`로 맞춘다(가능하면 한 모듈의 정규식을 공유한다).

### N-2 [HIGH, PLAUSIBLE → 런타임 세션이 CONFIRMED로 확인] 노드 보고 형식이 `# pass N`이 아니면 node 작업이 GREEN에 닿지 못한다
- 위치: `runner/tdd_gate.py:11`(`^# pass (\d+)$`).
- 근거: 이 개발 장비의 Node 26.5에서 `node -e "require('node:test')('x',()=>{})" | cat`(비 TTY)은 `ℹ tests 1 / ℹ pass 1`을 출력하고 `# pass`는 없다. 이 형식은 어떤 패턴에도 일치하지 않는다. 저장소의 테스트 입력은 TAP 형식(`# tests 4`, `# pass 4`)을 직접 쓴 문자열이다. 실제 `node:24-slim` 출력은 확인하지 못했다.
- 시나리오: 이미지가 spec 보고 형식이면 모든 통과한 `node --test`가 `NO_TESTS_RAN`이 된다. 모델은 이유를 모르고 같은 동작을 반복하다 `STREAK_LIMIT`으로 `needs_input`이 된다. python 작업은 영향이 없다.
- 확인: 이미지에서 `node --test`를 한 번 돌려 본다. 수정: `^[#ℹ] pass (\d+)$`를 허용하거나 `--test-reporter=tap`을 강제한다.
- 런타임 세션의 확인(2026-10-22): `node:24-slim`(v24.22.0)에서 `node --test`를 비 TTY로 실행 → `✔ x`, `ℹ tests 1`, `ℹ pass 1` 출력, exit 0. `count_tests(stdout, stderr)`는 `None`.

### N-3 [MEDIUM, CONFIRMED] `install_dependencies`가 쓴 잠금 파일이 개입(`outside_ledger`)으로 표시된다
- 위치: `runner/tools.py:178`(`self.workspace.write(lock_file, …)`는 원장의 `write_file`이 아니다)와 `runner/intervention.py:8-15`(`MUTATING`에 install이 없고, 명령이 있으면 건너뛰던 분기가 삭제됨).
- 시나리오: pip 의존성을 설치한 task에서 `requirements.lock`이 생긴다. 이 파일은 before/after 비교의 `changes`에 들어가고 원장 경로에 없다. `pipeline.py:~131`이 `outside_ledger` 개입과 "자율 수행 근거로 쓰지 않습니다" 경고를 붙인다. 기존 테스트는 이 경우를 다루지 않는다(`test_intervention`은 `.pytest_cache` 사례만 본다). npm 잠금은 64KB를 넘으면 쓰기가 조용히 실패하므로 덜 걸린다.
- 수정: `ledgered_paths`가 성공한 `install_dependencies`에 대해 `LOCK_FILES[manager]`를 설명 가능한 경로로 포함한다.

### N-4 [MEDIUM, CONFIRMED] RED는 테스트가 하나도 실행되지 않아도 얻을 수 있다
- 위치: `runner/tdd_gate.py:88-90`. `count_tests`는 exit 0일 때만 쓰이고, RED는 `code not in (0, None)`만 본다.
- 시나리오: 테스트 파일이 비어 있다. `python:3.13-slim`에서 `python -m unittest`는 "Ran 0 tests"에 exit 5로 끝난다. 이것이 RED가 된다. 구현을 쓰고, 그다음 테스트를 추가해 통과시키면 GREEN이다. 실패한 적 없는 테스트로 RED→GREEN이 성립한다. 존재하지 않는 모듈 이름을 넘긴 exit 1도 마찬가지로 RED가 된다.
- 수정: `tests_run == 0`이면 exit 코드와 상관없이 `NO_TESTS_RAN`으로 기록한다. unittest의 import 오류는 "Ran 1 test"로 세어지므로 정상 RED는 유지된다.

### N-5 [LOW, CONFIRMED] 개발용 격리 점검이 낡았다
- 위치: `infra/verify_isolation.py:84-86`. `/work/lc-x` 쓰기가 `ok`여야 통과하는 기대(`root_filesystem_read_only_work_and_tmp_writable`)가 읽기 전용 마운트와 맞지 않아 EROFS로 실패한다.
- 수정: `/work`는 `EROFS`를 기대하도록 바꾼다.

### N-6 [LOW, CONFIRMED] 접두사 재생성이 다른 접두사와 다시 충돌할 수 있다
- 위치: `runner/plan_extras.py:121-122`. 생성한 접두사는 `prefixes`와 비교하지 않는다.
- 시나리오: AC id가 `["a__3","a!","a?"]`이면 셋째가 `a__3`으로 재생성되어 첫째와 같아진다. 중복 id 검사(`plan_extras.py:127`, `worker.py:190`)가 막아서 조용히 통과하지는 않고, 계획이 422로 거부된다.
- 수정: `while prefix in prefixes:`로 반복한다.

### N-7 [LOW, CONFIRMED] 통과한 run_tests의 요약이 출력 상한에 잘릴 수 있다
- 위치: `runner/tools.py:128`. 개수 판독이 이미 64KB로 잘린 `public["stdout"]`와 `stderr`에서 이루어진다(`commands.py:157-159`).
- 시나리오: 요약이 끝에 오는 형식에서 노이즈가 64KB를 넘으면 개수를 못 찾아 `NO_TESTS_RAN`이 된다. 드문 경우다.
- 수정: 개수 판독은 잘리기 전 원본의 꼬리로 한다.

## 보지 못한 범위
- 테스트 스위트, Docker, Ollama를 실행하지 않았다. 읽기 전용 마운트에서 npm과 pip가 실제로 어떻게 동작하는지, `bounded_run`의 실제 타이밍은 실행으로 확인하지 못했다.
- `node:24-slim`의 비 TTY 보고 형식과 `python:3.13-slim`의 exit 5 동작은 실행하지 않았다. 앞의 것은 로컬 Node 26.5 출력과 알려진 동작에서, 뒤의 것은 알려진 동작에서 추정했다(N-2는 PLAUSIBLE).
- `runner/mcp_server.py`의 ToolBox 경로(동기 호출 여부), 프론트엔드, `release`와 프리뷰 경로, 후보 앱의 `/data` 볼륨 디스크 상한은 읽지 않았다.
- 새 테스트(`test_gate_hardening`, `test_resource_limits`, `test_review_fixes`)는 읽기만 했고 실행하지 않았다.
- M-1(재시도 task의 거짓 개입)과 M-2 이하는 이번 범위가 아니라 재검토하지 않았다.
