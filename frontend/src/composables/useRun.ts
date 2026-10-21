import { computed, ref, shallowRef } from 'vue'
import { ApiError } from '../api/errors'
import type { RunSource } from '../api/source'
import type { AcceptanceStatus, ChangePayload, Command, CommandReceipt, DecisionPayload, RunEvent, Snapshot } from '../api/types'
import { classifyEvent, isOlderSnapshot, needsSnapshot } from '../model/eventStream'

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
/** 누락 재동기화가 반복되면 재연결 간격을 늘린다(통신 제어일 뿐, 제품의 수정·실행 횟수 상한이 아님) */
const GAP_BACKOFF_BASE_MS = 500
const GAP_BACKOFF_MAX_MS = 30_000
/** 사건 목록 화면 갱신을 묶는 간격. 긴 이력 수신 때 매 사건 전체 재계산을 피한다 */
const EVENT_FLUSH_MS = 100

export function gapDelay(streak: number): number {
  return streak <= 1 ? 0 : Math.min(GAP_BACKOFF_MAX_MS, GAP_BACKOFF_BASE_MS * 2 ** (streak - 2))
}

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
  /** 판정 + 조회를 시작한 시점의 스냅샷 버전. 같은 버전의 스냅샷에서만 유효하다(CT36) */
  const acceptance = shallowRef<{ status: AcceptanceStatus; forVersion: number } | null>(null)
  const acceptanceError = shallowRef<ApiError | null>(null)
  /** 최초 연결 시점의 seq. 이보다 큰 사건만 장면에서 연출한다(기록 사건은 연출하지 않음) */
  const liveFromSeq = ref(Number.POSITIVE_INFINITY)
  const liveListeners = new Set<(event: RunEvent) => void>()

  let lastSeq = 0
  let closeStream: (() => void) | null = null
  let refreshing: Promise<void> | null = null
  let refreshAgain = false
  let disposed = false
  let pendingTimer: ReturnType<typeof setTimeout> | null = null
  let acceptanceToken = 0
  let gapStreak = 0
  let gapTimer: ReturnType<typeof setTimeout> | null = null
  let flushTimer: ReturnType<typeof setTimeout> | null = null

  /** 수신 원본. 제자리로 쌓고(O(1)/사건) 화면에는 묶음 간격마다 새 배열로 게시한다(자식 prop이 변경을 감지하도록) */
  let log: RunEvent[] = []

  function flushEvents(): void {
    if (flushTimer) clearTimeout(flushTimer)
    flushTimer = null
    if (events.value.length !== log.length || events.value.at(-1) !== log.at(-1)) events.value = log.slice()
  }

  function appendEvent(event: RunEvent): void {
    log.push(event)
    if (!flushTimer) flushTimer = setTimeout(flushEvents, EVENT_FLUSH_MS)
  }

  function clearPending(): void {
    if (pendingTimer) clearTimeout(pendingTimer)
    pendingTimer = null
    pending.value = null
  }

  function applySnapshot(next: Snapshot): void {
    const current = snapshot.value
    if (current && isOlderSnapshot(next, current)) return // 늦게 도착한 옛 스냅샷은 무시
    // 버전 증가만으로는 내 명령의 반영인지 알 수 없다(다른 작업도 버전을 올린다). 확인 표시는 건드리지 않는다.
    snapshot.value = next
    // 업무 상태나 명세가 바뀌었으면 AC 판정도 다시 읽는다
    if (!current || current.state_version !== next.state_version || current.spec_version_id !== next.spec_version_id) {
      void refreshAcceptance()
    }
  }

  /**
   * 가장 최근 요청의 응답만 반영한다(늦게 온 옛 응답이 새 화면에 섞이지 않게).
   * 판정은 조회를 시작한 스냅샷 버전에 묶는다. 같은 명세에서도 회차·보고서가 바뀌면 버전이 바뀌므로
   * 새 판정이 오기 전까지 옛 충족을 보여 주지 않는다. 조회 실패 시 옛 판정을 지운다.
   */
  async function refreshAcceptance(): Promise<void> {
    const token = ++acceptanceToken
    const forVersion = snapshot.value?.state_version ?? -1
    try {
      const status = await source.getAcceptance()
      if (token !== acceptanceToken || disposed) return
      acceptance.value = { status, forVersion }
      acceptanceError.value = null
    } catch (error) {
      if (token !== acceptanceToken || disposed) return
      acceptance.value = null
      acceptanceError.value = error instanceof ApiError ? error : new ApiError(0, 'NETWORK', 'AC 판정을 읽지 못했습니다.')
    }
  }

  /** 현재 스냅샷과 같은 버전·명세의 판정만 쓴다 */
  const validAcceptance = computed<AcceptanceStatus | null>(() => {
    const a = acceptance.value
    const snap = snapshot.value
    if (!a || !snap) return null
    return a.forVersion === snap.state_version && a.status.spec_version_id === snap.spec_version_id ? a.status : null
  })

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
      gapStreak += 1
      const delay = gapDelay(gapStreak)
      notice.value = `사건 ${verdict.expected}–${verdict.got - 1}번이 누락돼 다시 동기화합니다${delay ? ` (${Math.round(delay / 1000)}초 뒤, 반복 ${gapStreak}회)` : ''}.`
      closeStream?.()
      closeStream = null
      connection.value = 'resyncing'
      if (gapTimer) clearTimeout(gapTimer)
      const resume = () => {
        gapTimer = null
        reopen(lastSeq, 'resyncing')
        void refreshSnapshot()
      }
      if (delay === 0) resume()
      else gapTimer = setTimeout(resume, delay)
      return
    }
    gapStreak = 0
    lastSeq = event.seq
    appendEvent(event)
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
      onMalformed: () => {
        notice.value = '형식이 맞지 않는 사건을 받아 건너뛰었습니다. 누락이 생기면 다시 동기화합니다.'
      },
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
    log = log.filter((e) => e.seq <= lastSeq)
    flushEvents()
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
    if (gapTimer) clearTimeout(gapTimer)
    gapTimer = null
    gapStreak = 0
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
    if (gapTimer) clearTimeout(gapTimer)
    if (flushTimer) clearTimeout(flushTimer)
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
    /** 현재 스냅샷 버전·명세와 같은 판정만. 아니면 null(갱신 중·명세 전환 중·조회 실패) */
    acceptance: validAcceptance,
    /** 같은 버전에서 받은 판정인데 명세가 다르다(서버가 다른 명세의 판정을 줌) */
    acceptanceMismatch: computed(() => {
      const a = acceptance.value
      const snap = snapshot.value
      return !!a && !!snap && a.forVersion === snap.state_version && a.status.spec_version_id !== snap.spec_version_id
    }),
    /** 현재 스냅샷의 판정을 아직 받지 못함(오류 아님) */
    acceptancePending: computed(() => !!snapshot.value && !validAcceptance.value && !acceptanceError.value),
    acceptanceError,
    refreshAcceptance,
    /** 묶음 대기 중인 사건을 즉시 화면 목록에 게시한다 */
    flushEvents,
    start,
    reconnect,
    refreshSnapshot,
    send,
    onLiveEvent,
    dispose,
  }
}

export type RunController = ReturnType<typeof useRun>
