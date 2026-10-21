# 실제 Docker 격리·레지스트리 확인 기록 (모델 호출 없음)

실행: 2026-10-21, `infra/verify_isolation.py --network`, Docker Desktop 29.6.2(macOS, arm64). 이 문서는 해당 실행의 기록이며 Linux 호스트·다른 Docker 구성의 검증이 아니다.

고정 이미지(pull 후 RepoDigest):
- `python@sha256:cf50a4f6ac4f026458b08d5222023d700ac806410dff5e9ca8728fa44f2b850f` (python:3.13-slim)
- `node@sha256:91acba91b842bec0bf7ea6f5e09c644c7ccad72c4996ed9616d861d1c7cd60d4` (node:24-slim)

| 점검 | 결과 | 관측 근거 |
|---|---|---|
| python_runs_allowed_command | 통과 | `"42"` |
| node_runs_allowed_command | 통과 | `"42"` |
| policy_refuses_shell | 통과 | `"허용된 실행 파일이 아닙니다."` |
| network_none_blocks_egress | 통과 | `"blocked 101"` |
| runs_as_nobody_without_capabilities | 통과 | `{"uid": "65534", "cap_eff": "0000000000000000", "no_new_privs": "1"}` |
| root_filesystem_read_only_work_and_tmp_writable | 통과 | `"{'/etc/lc-x': 'EROFS', '/usr/lc-x': 'EROFS', '/tmp/lc-x': 'ok', '/work/lc-x': 'ok'}"` |
| memory_limit_kills_overuse | 통과 | `{"exit_code": 137}` |
| timeout_kills_the_container | 통과 | `{"timed_out": true, "leftover": []}` |
| plain_tool_container_has_no_route_out | 통과 | `"blocked"` |
| pip_install_through_allowlist_proxy | 통과 | `{"exit_code": 0, "lock": "six==1.17.0", "stderr": ""}` |
| installed_python_package_importable_offline | 통과 | `"1.17.0"` |
| npm_install_through_allowlist_proxy | 통과 | `{"exit_code": 0, "stderr": ""}` |
| installed_node_package_loadable_offline | 통과 | `"true"` |
| proxy_refuses_a_non_registry_host | 통과 | `{"client": "refused URLError", "proxy_log": [{"event": "tunnel", "target": ["registry.npmjs.org", 443]}, {"event": "tunnel", "target": ["registry.npmjs.org", 44` |
| every_call_is_in_the_ledger | 통과 | `{"entries": 13, "denied": 1}` |

확인 범위: 허용 명령 실행, 정책의 밖 명령 거부(`sh`), `--network none`의 외부 접속 차단, uid 65534·CapEff 0·NoNewPrivs 1, 읽기 전용 루트(EROFS)와 `/tmp`·`/work` 쓰기, 메모리 한도(512m, swap 포함 동일)에서 900MB 할당이 137로 종료, 타임아웃 시 컨테이너 kill과 잔여 컨테이너 없음, 일반 도구 컨테이너(내부 네트워크)의 외부 경로 없음, 허용 목록 프록시를 통한 실제 PyPI(`six`)·npm(`is-number`) 설치와 설치 후 오프라인 import/require, 프록시의 비레지스트리 호스트 거부와 로그.

실검증으로 발견해 고친 것:
1. `--memory 512m`만으로는 컨테이너 swap 때문에 900MB 할당이 통과했다(종료 코드 0). `--memory-swap`을 같은 값으로 고정했다(`Sandbox.limits`, 스캐너·검토 컨테이너의 별도 메모리 값도 인자로 전달).
2. 파이썬·노드 프로그램은 서로 다른 이미지가 필요해 `DockerExecutor`가 언어별 이미지 맵을 받는다.
3. 프록시 컨테이너가 jsonschema를 요구하지 않도록 `registry_hosts` 모듈로 분리해 표준 라이브러리만 쓴다.

확인하지 못한 것: Linux 호스트의 바인드 마운트 소유권(Docker Desktop에서는 uid 65534가 호스트 디렉터리에 쓸 수 있었다), 장시간 설치와 대용량 의존성(tmpfs 32MB 한도 안에서 작은 패키지만 확인), `--pids-limit` 소진 시나리오, 프록시의 운영 배포 방식(이번에는 검증용 임시 컨테이너).
