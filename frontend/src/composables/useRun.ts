import { computed, ref, shallowRef } from 'vue'
import { ApiError } from '../api/errors'
import type { RunSource } from '../api/source'
import type { ChangePayload, Command, CommandReceipt, DecisionPayload, RunEvent, Snapshot } from '../api/types'
import { classifyEvent, needsSnapshot } from '../model/eventStream'

/** 실행 상태와 별개의 연결 상태. 연결 끊김을 실행 실패로 표시하지 않는다. */
export type ConnectionState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'resyncing' | 'closed'

export interface PendingCommand {
  commandId: string
  action: Command['action']
  expectedStateVersion: number
  receipt: CommandReceipt | null
}

export type CommandInput =
  | { action: 'decide'; payload: DecisionPayload }
  | { action: 'request_changes'; payload: ChangePayload }
  | { action: 'pause' | 'resume' | 'cancel'; payload: Record<string, never> }

const PENDING_CONFIRM_MS = 20_000

export function newCommandId(): string {
  return crypto.randomUUID()
}

export function useRun(source: RunSource) {
  const snapshot = shallowRef<Snapshot | null>(null)
  const events = shallowRef<RunEvent[]>([])
  const connection = ref<ConnectionState>('idle')
  const loadError = shallowRef<ApiError | null>(null)
  const notice = ref<string | null>(null)
  const pending = shallowRef<PendingCommand | null>(null)
  /** 최초 연결 시점의 seq. 이보다 큰 사건만 장면에서 연출한다(기록 사건은 연출하지 않음) */
  const liveFromSeq = ref(Number.POSITIVE_INFINITY)
  const liveListeners = new Set<(event: RunEvent) => void>()

  let lastSeq = 0
  let closeStream: (() => void) | null = null
  let refreshing: Promise<void> | null = null
  let refreshAgain = false
  let disposed = false
  let pendingTimer: ReturnType<typeof setTimeout> | null = null

  function clearPending(): void {
    if (pendingTimer) clearTimeout(pendingTimer)
    pendingTimer = null
    pending.value = null
  }

  function applySnapshot(next: Snapshot): void {
    const current = snapshot.value
    if (current && next.state_version < current.state_version) return // 늦게 도착한 이전 버전은 무시
    // 버전 증가만으로는 내 명령의 반영인지 알 수 없다(다른 작업도 버전을 올린다). 확인 표시는 건드리지 않는다.
    snapshot.value = next
  }

  /** 동시에 여러 번 요청돼도 한 번에 하나만 읽고, 진행 중 요청이 있었으면 한 번 더 읽는다 */
  function refreshSnapshot(): Promise<void> {
    if (refreshing) {
      refreshAgain = true
      return refreshing
    }
    refreshing = (async () => {
      try {
        do {
          refreshAgain = false
          try {
            applySnapshot(await source.getSnapshot())
            loadError.value = null
          } catch (error) {
            loadError.value = error instanceof ApiError ? error : new ApiError(0, 'NETWORK', '스냅샷을 읽지 못했습니다.')
          }
        } while (refreshAgain && !disposed)
      } finally {
        // 루프 종료와 같은 틱에 비워야 그 사이 요청이 무시되지 않는다
        refreshing = null
      }
    })()
    return refreshing
  }

  function handleEvent(event: RunEvent): void {
    const verdict = classifyEvent(lastSeq, event)
    if (verdict.kind === 'duplicate') return
    if (verdict.kind === 'gap') {
      notice.value = `사건 ${verdict.expected}–${verdict.got - 1}번이 누락돼 다시 동기화합니다.`
      reopen(lastSeq, 'resyncing')
      void refreshSnapshot()
      return
    }
    lastSeq = event.seq
    events.value = [...events.value, event]
    const p = pending.value
    if (p && event.command_id === p.commandId) {
      clearPending()
      void refreshSnapshot()
    }
    if (needsSnapshot(snapshot.value, event)) void refreshSnapshot()
    if (event.seq > liveFromSeq.value) liveListeners.forEach((fn) => fn(event))
  }

  function reopen(afterSeq: number, state: ConnectionState): void {
    closeStream?.()
    if (disposed) return
    connection.value = state
    closeStream = source.openEvents(afterSeq, {
      onEvent: handleEvent,
      onOpen: () => {
        connection.value = 'open'
      },
      onDown: (closed) => {
        connection.value = closed ? 'closed' : 'reconnecting'
      },
      onResync: () => void resync(),
    })
  }

  async function resync(): Promise<void> {
    connection.value = 'resyncing'
    await refreshSnapshot()
    const snap = snapshot.value
    if (!snap || loadError.value) {
      connection.value = 'closed' // 낡은 커서로 다시 연결하지 않는다
      return
    }
    notice.value = '서버 기록 범위 밖이라 최신 스냅샷부터 다시 연결했습니다. 이전 사건 일부는 표시되지 않을 수 있습니다.'
    lastSeq = snap.last_event_seq
    events.value = events.value.filter((e) => e.seq <= lastSeq)
    reopen(lastSeq, 'connecting')
  }

  async function start(): Promise<void> {
    connection.value = 'connecting'
    await refreshSnapshot()
    if (!snapshot.value) {
      connection.value = 'closed'
      return
    }
    liveFromSeq.value = snapshot.value.last_event_seq
    // 기록 전체를 보여주기 위해 처음부터 받는다. 서버는 사건을 모두 보존한다(D1 §7).
    reopen(0, 'connecting')
  }

  /** 스냅샷(필요하면 세션 재발급 포함)을 먼저 읽고, 성공했을 때만 사건 스트림을 다시 연다 */
  async function reconnect(): Promise<void> {
    connection.value = 'connecting'
    await refreshSnapshot()
    if (loadError.value) {
      connection.value = 'closed'
      return
    }
    reopen(lastSeq, 'connecting')
  }

  /** 202는 접수일 뿐이다. 반영은 같은 command_id가 담긴 사건으로만 확인하고, 오지 않으면 시간 초과 뒤 "미확인"으로 푼다. */
  async function send(input: CommandInput, commandId: string): Promise<CommandReceipt> {
    const snap = snapshot.value
    if (!snap) throw new ApiError(0, 'INVALID_STATE', '스냅샷이 없어 명령을 보낼 수 없습니다.')
    const command = {
      kind: 'command',
      protocol_version: 1,
      command_id: commandId,
      run_id: snap.run_id,
      expected_state_version: snap.state_version,
      action: input.action,
      payload: input.payload,
    } as Command
    pending.value = { commandId, action: input.action, expectedStateVersion: snap.state_version, receipt: null }
    try {
      const receipt = await source.sendCommand(command)
      if (pending.value?.commandId === commandId) {
        pending.value = { ...pending.value, receipt }
        // 접수 뒤 반영 근거가 오지 않으면 조작을 다시 풀고 미확인임을 알린다(영구 잠금 방지)
        pendingTimer = setTimeout(() => {
          if (pending.value?.commandId !== commandId) return
          clearPending()
          notice.value = '명령은 접수됐지만 반영을 아직 확인하지 못했습니다. 실행 상태와 사건 기록을 확인하세요.'
        }, PENDING_CONFIRM_MS)
      }
      void refreshSnapshot()
      return receipt
    } catch (error) {
      if (pending.value?.commandId === commandId) clearPending()
      if (error instanceof ApiError && error.isStale) await refreshSnapshot()
      throw error
    }
  }

  function onLiveEvent(fn: (event: RunEvent) => void): () => void {
    liveListeners.add(fn)
    return () => liveListeners.delete(fn)
  }

  function dispose(): void {
    disposed = true
    if (pendingTimer) clearTimeout(pendingTimer)
    closeStream?.()
    closeStream = null
    liveListeners.clear()
  }

  return {
    source,
    snapshot,
    events,
    connection,
    loadError,
    notice,
    pending,
    liveFromSeq,
    /** 실제 기록 재생은 읽기 전용. 합성 예시는 조작 흐름을 보여주되 명령을 보내지 않는다(EXAMPLE_NOOP). */
    isReplay: computed(() => source.kind === 'live' && snapshot.value?.mode === 'replay'),
    start,
    reconnect,
    refreshSnapshot,
    send,
    onLiveEvent,
    dispose,
  }
}

export type RunController = ReturnType<typeof useRun>
