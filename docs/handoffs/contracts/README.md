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
