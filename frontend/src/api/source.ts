import type { AcceptanceStatus, Command, CommandReceipt, Environment, RecordingBundle, ReleaseView, RunEvent, Snapshot } from './types'

/** 화면의 연결 출처. LIVE/REPLAY 구분은 출처가 live일 때만 snapshot.mode로 한다. */
export type SourceKind = 'example' | 'live'

export interface StreamHandlers {
  onEvent(event: RunEvent): void
  /** 서버가 보존 구간 밖이라고 알렸다: 스냅샷부터 다시 읽는다 */
  onResync(): void
  onOpen(): void
  /** 연결 끊김. closed=true면 브라우저가 자동 재연결하지 않는다 */
  onDown(closed: boolean): void
  /** 계약 형식이 아닌 사건 데이터를 받아 건너뜀 */
  onMalformed?(): void
}

/** 합성 시연 전용 조작. 서버에는 아무것도 보내지 않는 시연 소스만 제공한다 */
export interface DemoInfo {
  /** 반영된 마지막 단계(-1이면 시작 전) */
  index: number
  total: number
  label: string
  /** 사람이 결정해야 멈춰 있는 단계. 없으면 null */
  waiting: 'plan' | 'acceptance' | null
  done: boolean
}
export interface DemoControl {
  /** 모든 화면에 계속 보이는 합성 표시 문구 */
  readonly badge: string
  info(): DemoInfo
  onChange(fn: () => void): () => void
  /** 기다리지 않고 다음 사건으로 넘어간다. 사람 결정 대기 중에는 아무 일도 하지 않는다 */
  next(): void
}

/** UI는 이 경계만 소비한다. 예시와 실제 API가 같은 Snapshot/Event를 준다. */
export interface RunSource {
  readonly kind: SourceKind
  readonly runId: string
  /** 있으면 합성 시연이다(자동 진행·다음 단계·합성 배지) */
  readonly demo?: DemoControl
  getSnapshot(): Promise<Snapshot>
  /** 현재 명세의 AC별 판정(CR-C09). 재생이면 기록 당시의 동결된 판정 */
  getAcceptance(): Promise<AcceptanceStatus>
  /** 공개 기록 묶음 내보내기. 합성 예시는 실제 기록이 아니므로 거절한다 */
  getRecording(): Promise<RecordingBundle>
  /** 출시·복구 공개 근거(읽기 전용). 실행·승인 엔드포인트가 아니다. 계약상 enabled=false 고정 */
  getRelease(): Promise<ReleaseView>
  openEvents(afterSeq: number, handlers: StreamHandlers): () => void
  sendCommand(command: Command): Promise<CommandReceipt>
  getArtifact(id: string): Promise<unknown>
  getEnvironment(id: string): Promise<Environment>
}
