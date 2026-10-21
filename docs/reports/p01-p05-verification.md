# P01–P05 통합 검증 범위

2026-10-21. 상태의 단일 원본은 [Codex 인계](../handoffs/codex.md)다. 이 문서는 측정과 재현 조건을 정리한다. 전체 사용자 수용·종합 보안·배포 완료 보고서가 아니다.

## POST-INTEGRATION 후속 확인

- 원래 요청 번호를 유지했다. **CR-C14=기획별 지원 공백**, **CR-C15=출시·복구 결과**. 계약 전용 8ff4ca1의 번호 충돌을 a6eb8a4에서 정정했다. HTTP SHA256 `f35c48532161dbc2adb6ff3c4538c8563541e8c9d05687a351ed2b96dda61c81`, protocol SHA256 `43e0f444b2f6fc408dd177d8db599a7a13f0f3e7e8f0e2993595701c89147147`. 아래 이전 검사 시점의 HTTP hash와 구분한다.
- b40e292 제공자: run별 고정 cafemap-v1, 기획에 동결한 PlanSupport와 승인 차단, planner의 실제 역할별 검색/공개 근거, 출시 원장 읽기 전용 GET과 operation 사건·artifact 연결을 추가했다. Runtime 템플릿 상태는 기획별 공백을 대체하지 않는다.
- f5a2bc0: Claude 완료 소비자 d625f74/4f396c8을 통합했다. 프론트 239개/5.99초, vue-tsc/Vite build 통과(JS gzip 74.95KB). frontend 파일을 직접 수정하지 않았다.
- 실제 S09 요청과 **“외부 연결은 나중에 결정”**을 보존했다. cafemap-v1은 공급자 미설정 경계/설정 저장을 준비한 스캐폴드이며 실제 지도·장소 검색/추천이 구현된 앱이 아니다. 가짜 장소/문의 CRUD를 사용하지 않는다. 외부 공급자·키/좌표 전송과 실제 배포는 비활성이다.
- 실제 로컬 qwen3.5:4b/단일 worker/로컬 qwen3-embedding:0.6b의 실행에서 검색 근거를 발급했다. 첫 시도는 최초 조각의 존재하지 않는 정정 증거로 차단했고 151cb86에서 최초 출력 revisions=[]를 스키마로 강제했다(62개/43.546초 통과). 다음 시도는 첫 조각을 보존한 뒤 두 번째 호출의 14,928bytes 예산 초과로 차단됐다. 실패 기록/원문은 보존했고 사람 승인·구현을 만들지 않았다. 후속 수정/실제 성공 여부는 최신 Codex 인계를 따른다.
- actual LIVE DB와 run 주소·실행 코드·프로세스 소유자/가동 상태의 단일 원본은 Codex 인계의 POST-INTEGRATION 절이다. 아래 옛 제출 후보는 이번 확장과 새 수용 근거를 포함하지 않는다.

## 기준과 검증

- 원본 main/초기 backend·runner 초안은 보존했다. 제품 구현은 work/codex-runtime worktree에서만 수행했다. frontend는 Claude 완료 커밋만 병합했고 소스·lock·생성 타입을 직접 수정하지 않았다.
- `a514b05`: 공개 검색/문맥 근거, 기록 HTTP/CLI 이동, 취소 프리뷰 조정, 비활성 출시 어댑터.
- `b7f01f0`: Claude `d85ea5a`/`c054287` 계약 소비자 병합. 공유 전송 문서의 등록 예정/등록 완료 한 문장 충돌만 최신 제공자 내용으로 해소했다.
- `914a269`: Claude 오류 안내 efb73f4와 최종 인계 900425a까지 병합했다.
- `ca0946b`: 사용자정보가 있는 저장소 URL/완료 조각 수 초과를 import에서 거절하고 보고서를 기록했다.
- `512b397`: Claude 7da9bac의 기록 공유 전 내용 검토 안내를 통합했다.
- `6069b04`: Git 정보 없는 사본이 상위 저장소 버전을 주장하지 않도록 수정. 1,200개 추가 사건의 페이지 조회·이동도 검사했다.
- protocol SHA256 `43e0f444b2f6fc408dd177d8db599a7a13f0f3e7e8f0e2993595701c89147147`, HTTP SHA256 `2b8516cebbb75cb28f1c20ac371706532063f65f3ffa4c425e75f0f37ab2cddc`. 제공자·Claude 생성 해시가 같다.
- b7f01f0에서 백엔드 55개(49.099초), 통합 frontend 203개(6.45초), vue-tsc/Vite build 통과. gzip JS 70.05 KB. 최종 백엔드 전체 57개(43.294초), 후속 archive 경계 보완 6개(5.544초), 7da9bac까지 통합한 frontend 217개(5.78초)·타입/빌드도 통과했다. 최종 gzip JS 70.37 KB.
- 개발 검사는 fake 모델·mock Git/Docker 등 합성 fixture와 실제 MCP stdio를 사용한다. 테스트에 저장한 결정/PASS는 실제 사용자 승인이나 제품 독립 검토 근거가 아니다.

## 실제 별도 환경 기록 열람

Python 3.14의 새 venv에 기존 requirements.lock을 설치했고 pip check가 통과했다. Git archive 사본과 빌드된 신뢰 사무실, 별도 새 DB를 사용했다. worker·모델·외부 키를 설정하지 않았고 API는 loopback 8016에서만 열었다.

기록은 과거 실제 로컬 모델/Docker로 수행한 **합성 개발 실행**의 공개 원장이다. 최초 문의 앱과 CSS 수정 뒤의 두 보고서·후보/사건을 포함한다. 스크립트 결정은 실제 사용자 승인으로 승격하지 않는다. 키·원본 DB·요청/시도 prompt·모델 가중치·cache·venv를 제출물에 넣지 않는다.

- b7f01f0의 clean exporter로 원본 DB를 read-only export하고 새 DB로 import했다. manifest `sha256:da48d60adf31d97c24ff2a4b053281bea3b31af7849b8fe6d0340cc81b5f48fb`. 원본 계획의 과거 계약 hash는 그대로 보존한다. exporter는 내보낸 코드이며 과거 원장 생성 버전이 아니다.
- 실제 Chrome에서 가져온 기록 목록/서명 없음·읽기 전용, 동결된 6개 AC와 동일 후보의 두 보고서를 확인했다. iframe 0개, 측정 당시 문서 가로 넘침 없음. 이는 최신 LIVE 수용을 대신하지 않는다.
- UI 내보내기는 manifest와 "내보냄"을 표시했다. 자동화의 download event는 시간 초과여서 다운로드된 로컬 파일 확인은 미실행이다.
- 브라우저 파일 선택은 확장 파일 접근 권한이 없어 막혔다. 권한을 넓히거나 다른 도구로 우회하지 않았다. CLI import와 API 크기·CSRF·멱등/읽기 전용 검사는 별도 통과했다.
- 상위 저장소 버전 오인 문제를 이 확인 중 발견해 6069b04로 수정했다. 수정된 24e7e6c 사본의 실제 HTTP import/export 200, 재생 명령 409 REPLAY_READ_ONLY, exporter revision=null을 확인했다. 11사건/9공개 artifact/2보고서를 읽었고 iframe은 0개였다. 새 기록 digest는 `sha256:fc46fa492b9f1b7029ff0da47ba6e71a38c00d5f5a6d62f794c559ef424c21e3`다. 후속 사용자정보 URL/조각 계수 거절은 관련 6개 자체 검사로 확인했다.

ca0946b의 별도 새 빈 DB에서도 실제 HTTP를 재확인했다: import/export 200, 동일 manifest 멱등, resume 409, jobs/commands/grants/operations 모두 0건, exporter revision=null. Chrome의 기록 11건/동결 AC·보고서/서명 없음·읽기 전용/iframe 0을 확인했다. capsule digest `sha256:85aa57a613370d3d30c6fd4c9e9bd89c49ed651eef63a9c2b51a4ce1a6b971ea`. 최종 914a269의 backend/runner는 ca0946b와 바이트가 같다. 자체 API/탭은 종료했다.

## 남은 수용 조건

- CT36/CT40 코드와 회귀는 통합됐다. 실제 모델의 다양한 정정 품질과 최신 LIVE 스타일 수정/재검토의 화면 수용은 별도다.
- CT46 프론트 guard 보완 a8e1590을 24e7e6c에 통합했다. 잘못된 역할/형식 거절 회귀를 포함하며 source/lock/타입은 직접 편집하지 않았다.
- 실제 S09 카공지도 요청은 보존했으나 현재 문의 CRUD 템플릿의 지원 범위를 벗어난다. 지도/위치·장소 검색/추천을 제공하는 도구·데이터 공급자의 무료 자격/권한과 격리 경계를 준비하고 실제 기획 승인을 받아야 한다. 지도 기능이 구현됐다고 표시하지 않는다.
- S10 출시 어댑터는 고정 Git/불변 registry 조회·기존 보호 프록시/내부망을 사용하는 로컬 Docker 첫 출시·unpublish/볼륨 보존만 지원한다. 실제 대상/무료 자격·push의 자동 배포 효과·정확한 HITL이 없어 제품 배포 API/worker는 비활성이다. 실제 push/deploy/rollback과 registry upload·cloud·이전 버전/데이터 이전은 미실행이다.
- 실제 Docker 응답 유실/장기 프로세스 장애·장비 전체 메모리 경합·실기기/타 브라우저/스크린리더·전체 S11 사용자 완주는 미확인이다. 문맥/한 파일 자체가 호출 예산을 넘으면 잘라내지 않고 needs_input으로 남긴다.

Claude 최종 인계의 임시 파일 서버 접근 제한 우회 정정은 기록으로만 받아들였다. 해당 경로를 파일 선택 수용 근거로 사용하지 않는다. 본 세션의 file chooser 실패는 미확인으로 보존하며 권한 변경/우회를 하지 않았다.

## 제출 후보

`runtime-data/submission-check/skala-lifecycle-review.tar.gz`와 `.sha256`을 제공한다. 포함한 코드의 revision, public recording manifest, 파일별 hash는 `CHECKSUMS.json`, 실제 분리 환경 확인은 `KEYLESS_CHECK.json`을 따른다. 키·원본 DB·가중치·venv·node_modules/cache는 제외한다. 실제 배포/전체 사용자 수용의 증거로 취급하지 않는다.

## 열람 재현

[backend README](../../backend/README.md)의 키·모델 없는 기록 열람 절을 따른다. API만 실행해 사무실에서 기록을 연다. CLI export/import, 최대 16 MiB, 서명 없는 출처/해시·개인 로컬 모드 경계를 확인한다. LIVE는 별도로 로컬 Qwen/DeepSeek·Ollama/단일 슬롯, 격리 이미지·scanner DB와 worker가 필요하다. 배포가 자동 활성화되지는 않는다.
