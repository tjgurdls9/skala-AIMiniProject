import { ApiError } from '../api/errors'
import type { RunSource } from '../api/source'
import type { ExampleScenario } from './scenarios'

const TAIL_INTERVAL_MS = 2600

/**
 * 합성 예시 출처. 네트워크를 쓰지 않으며 명령은 보내지 않는다(외부 승인·배포 없음).
 * 연결 후 기록 사건을 즉시, tail 사건을 일정 간격으로 흘려 장면 연출만 보여준다.
 */
export function exampleSource(scenario: ExampleScenario): RunSource {
  return {
    kind: 'example',
    runId: scenario.snapshot.run_id,
    getSnapshot: async () => scenario.snapshot,
    getAcceptance: async () => scenario.acceptance,
    getRecording: async () => {
      throw new ApiError(0, 'EXAMPLE_NOOP', '합성 예시는 실제 기록이 아니어서 내보내지 않습니다.')
    },
    openEvents(afterSeq, handlers) {
      const timers: ReturnType<typeof setTimeout>[] = []
      timers.push(setTimeout(() => {
        handlers.onOpen()
        scenario.events.filter((e) => e.seq > afterSeq).forEach((e) => handlers.onEvent(e))
      }, 0))
      scenario.tail
        .filter((e) => e.seq > afterSeq)
        .forEach((e, i) => timers.push(setTimeout(() => handlers.onEvent(e), TAIL_INTERVAL_MS * (i + 1))))
      return () => timers.forEach(clearTimeout)
    },
    sendCommand: async () => {
      throw new ApiError(0, 'EXAMPLE_NOOP', '합성 예시에서는 명령을 보내지 않았습니다.')
    },
    getArtifact: async (id) => {
      if (id in scenario.artifactBodies) return scenario.artifactBodies[id]
      throw new ApiError(404, 'NOT_FOUND', '합성 예시에는 이 산출물의 본문이 없습니다. 요약만 표시합니다.')
    },
    getEnvironment: async (id) => {
      const env = scenario.environments[id]
      if (env) return env
      throw new ApiError(404, 'NOT_FOUND', '환경 정보가 없습니다.')
    },
  }
}
