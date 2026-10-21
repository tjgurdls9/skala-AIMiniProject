# 로컬 격리 실행 준비

Codex worktree 루트에서 Docker Desktop과 loopback Ollama가 실행 중이어야 한다. 모델·이미지·DB는 자동 다운로드하지 않는다. 외부 유료 API와 배포는 비활성이다.

```sh
ollama pull qwen3.5:4b
docker pull python:3.11-alpine
docker pull anchore/grype:v0.121.0
backend/.venv/bin/python -m runner.sandbox prepare
backend/.venv/bin/python -m runner.review prepare-scanner
```

실제 내려받은 base/image digest, Dockerfile 해시를 `runtime-data/runtime-image.json`에 기록한다. 실행 때 입력 해시가 달라지면 재준비를 요구한다. 새 이미지가 안전하다고 추정하지 않으며 후보별 원본 Grype 보고서를 보존한다. Grype DB 준비만 공개 서버에 연결하고 실제 검사는 network none·읽기 전용 DB/이미지 tar를 사용한다. 168시간보다 오래된 DB, 도구 오류, 미실행은 통과가 아니다. High/Critical 일치 항목은 근거 없는 예외 없이 출시를 차단한다.

기본 이미지는 불필요한 OS 패키지를 줄인 [공식 Alpine 변형](https://hub.docker.com/_/python)이다. musl을 사용하므로 임의 스택의 호환성을 보장하지 않는다. 이 이미지는 프리뷰 프록시 실행용이다. 후보 검증·보안 검사는 고정 digest의 python/node 이미지에서 승인된 점검 명세로 수행한다. zlib는 스캐너가 제시한 수정 버전 `1.3.2-r1`을 Alpine의 서명 저장소에서 고정 설치한다. 핀이 사라지면 준비가 실패하며 자동으로 다른 버전을 선택하지 않는다. 이전 Debian 후보의 취약점/반려 보고서는 원장에 보존한다.

생성 코드는 비권한 사용자·읽기 전용 root·cap drop·no-new-privileges·CPU/메모리/PID/임시 공간 제한으로 실행한다. 후보에는 자기 `/data` 볼륨만 쓰기 가능하다. 검증기는 보호된 외부 파일이고 후보가 수정하지 못한다. 데이터 볼륨은 자동 삭제하지 않는다. 정적 AST/비밀 패턴 검사는 보수적인 범위 검사이며 종합 SAST나 무취약성 보증이 아니다.

프리뷰는 고정 대상만 연결하는 신뢰 프록시로 CSP·CORS를 강제한다. 운영자 쿠키를 전달하지 않고 외부 리디렉션·임의 호스트·응답 과대 전송을 허용하지 않는다. 코드 검토 통과 전 제품 프리뷰를 발급하지 않는다. 기존 사용자 컨테이너·볼륨은 정리하지 않는다.

모델 출처: [Qwen3.5:4b](https://ollama.com/library/qwen3.5:4b). 스캐너 출처: [Anchore Grype](https://github.com/anchore/grype).
