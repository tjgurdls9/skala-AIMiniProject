import { ApiError, toApiError } from './errors'
import { parseEventData } from '../model/eventStream'
import type { RunSource, StreamHandlers } from './source'
import type {
  AcceptanceStatus,
  Command, CommandReceipt, Environment, Project, ProjectCreate, ReplayRecording, RunCreate, Runtime, Session, Snapshot,
} from './types'

const EVENT_SOURCE_CLOSED = 2 // EventSource.CLOSED

type Fetch = typeof fetch
type EventSourceFactory = (url: string) => EventSource

/**
 * 로컬 API 클라이언트 (D1 계약 §7). 같은 origin의 /api 프록시만 호출한다.
 * 인증은 HttpOnly 세션 쿠키, 변경 요청은 메모리에만 둔 CSRF 토큰. 토큰을 저장소·URL에 넣지 않는다.
 */
export class LiveApi {
  private csrf: string | null = null
  private readonly fetchFn: Fetch
  private readonly makeEventSource: EventSourceFactory

  constructor(fetchFn: Fetch = (...args) => fetch(...args), makeEventSource: EventSourceFactory = (url) => new EventSource(url)) {
    this.fetchFn = fetchFn
    this.makeEventSource = makeEventSource
  }

  /** 새로고침 시 기존 세션의 CSRF를 읽고, 없으면 로컬 세션을 새로 연다 */
  async connect(): Promise<void> {
    try {
      this.csrf = (await this.raw<Session>('GET', '/api/session')).csrf_token
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error
      this.csrf = (await this.raw<Session>('POST', '/api/session')).csrf_token
    }
  }

  getRuntime(): Promise<Runtime> {
    return this.request('GET', '/api/runtime')
  }

  listReplays(): Promise<ReplayRecording[]> {
    return this.request('GET', '/api/replays')
  }

  createProject(body: ProjectCreate): Promise<Project> {
    return this.request('POST', '/api/projects', body)
  }

  createRun(projectId: string, body: RunCreate): Promise<Snapshot> {
    return this.request('POST', `/api/projects/${encodeURIComponent(projectId)}/runs`, body)
  }

  getSnapshot(runId: string): Promise<Snapshot> {
    return this.request('GET', `/api/runs/${encodeURIComponent(runId)}`)
  }

  getAcceptance(runId: string): Promise<AcceptanceStatus> {
    return this.request('GET', `/api/runs/${encodeURIComponent(runId)}/acceptance`)
  }

  sendCommand(runId: string, command: Command): Promise<CommandReceipt> {
    return this.request('POST', `/api/runs/${encodeURIComponent(runId)}/commands`, command)
  }

  getArtifact(id: string): Promise<unknown> {
    return this.request('GET', `/api/artifacts/${encodeURIComponent(id)}`)
  }

  getEnvironment(id: string): Promise<Environment> {
    return this.request('GET', `/api/environments/${encodeURIComponent(id)}`)
  }

  /** 최초 ?after=, 이후 재접속은 브라우저가 Last-Event-ID를 보낸다. heartbeat 주석은 EventSource가 걸러 낸다. */
  openEvents(runId: string, afterSeq: number, handlers: StreamHandlers): () => void {
    const es = this.makeEventSource(`/api/runs/${encodeURIComponent(runId)}/events?after=${afterSeq}`)
    es.addEventListener('lifecycle', (msg) => {
      const event = parseEventData((msg as MessageEvent<string>).data, runId)
      if (event) handlers.onEvent(event)
      else handlers.onMalformed?.()
    })
    es.addEventListener('resync', () => {
      es.close()
      handlers.onResync()
    })
    es.onopen = () => handlers.onOpen()
    es.onerror = () => handlers.onDown(es.readyState === EVENT_SOURCE_CLOSED)
    return () => es.close()
  }

  /** 401이면 세션을 한 번 다시 열고 재시도한다 */
  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    if (method !== 'GET' && this.csrf === null) await this.connect()
    try {
      return await this.raw<T>(method, path, body)
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error
      await this.connect()
      return this.raw<T>(method, path, body)
    }
  }

  private async raw<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    if (method !== 'GET' && this.csrf) headers['X-CSRF-Token'] = this.csrf
    let response: Response
    try {
      response = await this.fetchFn(path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        credentials: 'same-origin',
      })
    } catch {
      throw new ApiError(0, 'NETWORK', '서버에 연결하지 못했습니다.')
    }
    if (response.status === 204) return undefined as T
    const parsed: unknown = await response.json().catch(() => null)
    if (!response.ok) throw toApiError(response.status, parsed)
    if (parsed === null) throw new ApiError(response.status, 'BAD_RESPONSE', '빈 응답을 받았습니다.')
    return parsed as T
  }
}

export function liveSource(api: LiveApi, runId: string): RunSource {
  return {
    kind: 'live',
    runId,
    getSnapshot: () => api.getSnapshot(runId),
    getAcceptance: () => api.getAcceptance(runId),
    openEvents: (after, handlers) => api.openEvents(runId, after, handlers),
    sendCommand: (command) => api.sendCommand(runId, command),
    getArtifact: (id) => api.getArtifact(id),
    getEnvironment: (id) => api.getEnvironment(id),
  }
}
