# P01 / S02 제공자 계약

기준 제공자: `c3e11c12ae18b5b2e8377931f870d9734e6b7d68`. 소비자 출발점은 `2403a0e`와 같은 계약을 가진 `f151930`이다. 전체 backend/runner 커밋을 가져올 필요 없이 아래 패치만 적용한다.

```sh
git apply --check /절대경로/v1-c3e11c1-from-2403a0e.patch
git apply /절대경로/v1-c3e11c1-from-2403a0e.patch
```

패치는 `docs/planning/http.v1.schema.json`, `docs/planning/contracts.md`만 변경한다. protocol은 변경 없음. CR-C09 AcceptanceStatus·GET, CR-C10 Preview 본문, CR-C11 command_id 사건 보장·멱등/POST-SSE 순서가 포함된다. Snapshot/Command/Event 필드 변경은 없다. 타입/해시 재생성·API/예시·AC 표시·CODEX-UI-001은 Claude 담당이다.

| 파일 | SHA256 |
|---|---|
| protocol.v1.schema.json | ad6decc2849e1eb80af54b557c7cc61ee05e7ac2b70e92abdddeedd3990bb07d |
| http.v1.schema.json | a7f384026fbde0f6dfe0c29f853c42911b000fefa0a95ee792424fb5dc909b4f |
| 패치 | 72976f6e210da86c2d5a6e8c039489fdcfa3e73836d87c36e7c73ebc693f2d0c |

현재 Claude의 계약 전용 `dc1407c`가 이미 같은 계약을 반영했다. 해당 worktree의 reverse apply check가 통과한다. 따라서 이 커밋을 가진 소비자는 패치를 다시 적용하지 않는다. 미완성 frontend 변경을 복사/병합하지 않았다. 소비자 완료 커밋·생성 해시 확인 후 Codex가 통합한다.

## CR-C12 (S04–S05) / CR-C13 응답

계약 전용 커밋 **`573c169a90cd008131fc81103a90feeb98f81595`** 또는 `v1-cr-c12.patch`만 반영한다. 출발 계약은 위 `a7f384…`다. HTTP `RetrievalEvidence`/`ContextEvidence` 정의를 추가했으며 protocol은 그대로다. 새 HTTP SHA256: **`9c5f15539411010c8216c8c116e94c26585ff59085ad904a896acefeca101662`**.

Claude 요청: 기존 고정 도구로 타입/해시를 재생성하고 두 artifact의 본문·출처/ACL·found/no_results/search_error·ready/needs_input·조각 진행도를 연결한 완료 커밋을 인계한다. raw prompt/추론은 제공되지 않는다. 현재 제공자 근거는 비공개로 저장하며 소비자 완료 뒤 공개 작업 연결을 활성화한다. Git/배포 타입이나 새 승인 필드는 이 계약에 포함하지 않았다.

CR-C13은 필드 변경 없이 원본 마지막 사건 시각으로 안정화했다(`96577be`). 계약 §7 끝의 정의를 사용하며 GET 호출 시각을 녹화 시각으로 표시하지 않는다. P01 소비자 및 직접 사용자 디자인 커밋 `0dbe45e`까지 `c4941bb`로 통합했다. 이 파일 작성은 Claude CLI로의 자동 전달이 아니다.


## S12 기록 이동 / 소비자 채택

계약 전용 `ce6dcc1`은 `573c169` 다음에 적용한다. Claude는 각각 `bb08f11`, `f10a741`로 채택하고 `d85ea5a`에서 소비자 타입/해시와 근거 UI·파일 import/export를 연결했다.

- protocol SHA256: `43e0f444b2f6fc408dd177d8db599a7a13f0f3e7e8f0e2993595701c89147147`
- HTTP SHA256: `2b8516cebbb75cb28f1c20ac371706532063f65f3ffa4c425e75f0f37ab2cddc`
- `GET /api/runs/{id}/recording`, `POST /api/recordings/import`는 기존 세션/CSRF 경계를 사용한다. 가져온 기록은 서명 없는 읽기 전용이며 생성 코드/프리뷰/승인/명령을 실행하지 않는다. 동일 manifest는 같은 import 결과를 돌려준다.

위 CR-C12의 비공개 저장/소비자 대기 문구는 당시 이력이다. 현재 제공자는 검증된 본문만 공개 artifact와 사건/작업에 연결한다. CLI/별도 포트 같은 origin 열람 조건은 backend README와 contracts §7을 따른다.
