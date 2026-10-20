import { describe, expect, test, vi } from 'vitest'
import { ApiError } from '../src/api/errors'
import { LiveApi, liveSource } from '../src/api/live'
import { buildEvents } from '../src/examples/base'

const CSRF = 'x'.repeat(40)
const json = (status: number, body: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function fakeFetch(routes: Array<(url: string, init: RequestInit) => Response | undefined>) {
  const calls: Array<{ url: string; init: RequestInit }> = []
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input)
    calls.push({ url, init })
    for (const route of routes) {
      const res = route(url, init)
      if (res) return res
    }
    return json(404, { error: { code: 'NOT_FOUND', message: '없음' } })
  })
  return { fn: fn as unknown as typeof fetch, calls }
}

const header = (init: RequestInit, name: string) => (init.headers as Record<string, string>)[name]

describe('로컬 세션과 CSRF (CR-C01)', () => {
  test('세션이 없으면 POST /api/session으로 연 뒤 CSRF를 변경 요청 헤더에만 싣는다', async () => {
    const { fn, calls } = fakeFetch([
      (u, i) => (u === '/api/session' && i.method === 'GET' ? json(401, { error: { code: 'UNAUTHORIZED', message: '세션 없음' } }) : undefined),
      (u, i) => (u === '/api/session' && i.method === 'POST' ? json(201, { csrf_token: CSRF, expires_at: '2026-10-20T18:00:00Z' }) : undefined),
      (u) => (u === '/api/projects' ? json(201, { project_id: 'p1', title: 't', created_at: '2026-10-20T00:00:00Z' }) : undefined),
      (u) => (u === '/api/runtime' ? json(200, { live_available: false }) : undefined),
    ])
    const api = new LiveApi(fn)
    await api.connect()
    await api.createProject({ title: 't', request: 'r' })
    await api.getRuntime()
    const post = calls.find((c) => c.url === '/api/projects')!
    expect(header(post.init, 'X-CSRF-Token')).toBe(CSRF)
    expect(JSON.parse(String(post.init.body))).toEqual({ title: 't', request: 'r' })
    expect(header(calls.find((c) => c.url === '/api/runtime')!.init, 'X-CSRF-Token')).toBeUndefined()
    expect(calls.every((c) => c.init.credentials === 'same-origin')).toBe(true)
  })

  test('변경 요청 중 401이면 세션을 다시 열고 한 번만 재시도한다', async () => {
    let commandCalls = 0
    const { fn } = fakeFetch([
      (u, i) => (u === '/api/session' && i.method === 'GET' ? json(200, { csrf_token: CSRF, expires_at: 'x' }) : undefined),
      (u) => {
        if (!u.endsWith('/commands')) return undefined
        commandCalls += 1
        return commandCalls === 1
          ? json(401, { error: { code: 'UNAUTHORIZED', message: '만료' } })
          : json(202, { command_id: 'c1', run_id: 'r1', status: 'accepted', accepted_at: 'x' })
      },
    ])
    const api = new LiveApi(fn)
    const receipt = await api.sendCommand('r1', { kind: 'command' } as never)
    expect(receipt.status).toBe('accepted')
    expect(commandCalls).toBe(2)
  })

  test('세션 조회의 401 외 오류는 그대로 전달한다', async () => {
    const { fn } = fakeFetch([(u) => (u === '/api/session' ? json(503, { error: { code: 'TEMPORARILY_UNAVAILABLE', message: '점검' } }) : undefined)])
    await expect(new LiveApi(fn).connect()).rejects.toMatchObject({ code: 'TEMPORARILY_UNAVAILABLE' })
  })
})

describe('HTTP 경계', () => {
  test('409 오류 본문을 ApiError로 바꾸고 현재 버전을 보존한다', async () => {
    const { fn } = fakeFetch([
      (u, i) => (u === '/api/session' && i.method === 'GET' ? json(200, { csrf_token: CSRF, expires_at: 'x' }) : undefined),
      (u) => (u.endsWith('/commands') ? json(409, { error: { code: 'VERSION_CONFLICT', message: '버전', current_state_version: 9 } }) : undefined),
    ])
    const err = await new LiveApi(fn).sendCommand('r1', {} as never).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect([err.code, err.currentStateVersion]).toEqual(['VERSION_CONFLICT', 9])
  })

  test('네트워크 실패는 NETWORK 오류다 (실행 실패로 해석하지 않는다)', async () => {
    const fn = vi.fn(async () => {
      throw new TypeError('fetch failed')
    }) as unknown as typeof fetch
    await expect(new LiveApi(fn).getRuntime()).rejects.toMatchObject({ code: 'NETWORK', status: 0 })
  })

  test('ID는 경로에 인코딩해 넣는다', async () => {
    const { fn, calls } = fakeFetch([(u) => json(200, { url: u })])
    const api = new LiveApi(fn)
    await api.getSnapshot('a/b')
    await api.getArtifact('x y')
    await api.getEnvironment('e?1')
    await api.listReplays()
    expect(calls.map((c) => c.url)).toEqual(['/api/runs/a%2Fb', '/api/artifacts/x%20y', '/api/environments/e%3F1', '/api/replays'])
  })

  test('204와 빈 본문을 구분한다', async () => {
    const { fn } = fakeFetch([
      (u, i) => (u === '/api/session' && i.method === 'GET' ? json(200, { csrf_token: CSRF, expires_at: 'x' }) : undefined),
      (u) => (u.includes('/runs/') ? new Response('', { status: 200 }) : undefined),
      (u) => (u.endsWith('/runs') ? new Response(null, { status: 204 }) : undefined),
    ])
    const api = new LiveApi(fn)
    await expect(api.getSnapshot('r')).rejects.toMatchObject({ code: 'BAD_RESPONSE' })
    await expect(api.createRun('p', { mode: 'live' })).resolves.toBeUndefined()
  })
})

class FakeEventSource {
  readyState = 0
  closed = false
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  private listeners = new Map<string, Array<(m: MessageEvent<string>) => void>>()
  constructor(readonly url: string) {}
  addEventListener(type: string, fn: (m: MessageEvent<string>) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn])
  }
  emit(type: string, data: string) {
    this.listeners.get(type)?.forEach((fn) => fn({ data } as MessageEvent<string>))
  }
  close() {
    this.closed = true
    this.readyState = 2
  }
}

describe('SSE 연결 (CR-C05)', () => {
  test('?after=로 시작하고 lifecycle 사건만 전달하며 resync에서 닫는다', () => {
    let es: FakeEventSource | null = null
    const api = new LiveApi(vi.fn() as unknown as typeof fetch, (url) => {
      es = new FakeEventSource(url)
      return es as unknown as EventSource
    })
    const handlers = { onEvent: vi.fn(), onResync: vi.fn(), onOpen: vi.fn(), onDown: vi.fn() }
    const source = liveSource(api, 'example-run')
    const close = source.openEvents(4, handlers)
    const sse = es as unknown as FakeEventSource
    expect(sse.url).toBe('/api/runs/example-run/events?after=4')

    const [event] = buildEvents([['warning', 'w', {}]], 5)
    sse.onopen?.()
    sse.emit('lifecycle', JSON.stringify(event))
    sse.emit('lifecycle', 'not json')
    expect(handlers.onOpen).toHaveBeenCalledOnce()
    expect(handlers.onEvent).toHaveBeenCalledExactlyOnceWith(event)

    sse.onerror?.()
    expect(handlers.onDown).toHaveBeenLastCalledWith(false)
    sse.emit('resync', JSON.stringify({ reason: 'cursor_out_of_range' }))
    expect(sse.closed).toBe(true)
    expect(handlers.onResync).toHaveBeenCalledOnce()
    sse.onerror?.()
    expect(handlers.onDown).toHaveBeenLastCalledWith(true)
    close()
  })
})
