import type { Command, CommandReceipt, Environment, RunEvent, Snapshot } from './types'

/** 화면의 연결 출처. LIVE/REPLAY 구분은 출처가 live일 때만 snapshot.mode로 한다. */
export type SourceKind = 'example' | 'live'

export interface StreamHandlers {
  onEvent(event: RunEvent): void
  /** 서버가 보존 구간 밖이라고 알렸다: 스냅샷부터 다시 읽는다 */
  onResync(): void
  onOpen(): void
  /** 연결 끊김. closed=true면 브라우저가 자동 재연결하지 않는다 */
  onDown(closed: boolean): void
}

/** UI는 이 경계만 소비한다. 예시와 실제 API가 같은 Snapshot/Event를 준다. */
export interface RunSource {
  readonly kind: SourceKind
  readonly runId: string
  getSnapshot(): Promise<Snapshot>
  openEvents(afterSeq: number, handlers: StreamHandlers): () => void
  sendCommand(command: Command): Promise<CommandReceipt>
  getArtifact(id: string): Promise<unknown>
  getEnvironment(id: string): Promise<Environment>
}
