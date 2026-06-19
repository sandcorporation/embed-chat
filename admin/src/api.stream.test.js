import { describe, it, expect, beforeEach, vi } from 'vitest'
import { openEscalationStream } from './api'
import { setAccess, refresh } from './auth'

class FakeEventSource {
  static instances = []
  constructor(url) {
    this.url = url
    this.closed = false
    this.listeners = {}
    FakeEventSource.instances.push(this)
  }
  addEventListener(type, cb) { this.listeners[type] = cb }
  close() { this.closed = true }
}

beforeEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
  FakeEventSource.instances = []
  globalThis.EventSource = FakeEventSource
})

describe('openEscalationStream — silent refresh 시 재오픈', () => {
  it('agent access가 refresh로 바뀌면 새 토큰으로 재오픈하고 이전 연결을 닫는다', async () => {
    setAccess('agent', 'tok1')
    const handle = openEscalationStream(() => {})

    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0].url).toContain('token=tok1')

    // silent refresh 발생 → 새 access
    globalThis.fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ access_token: 'tok2' }) })
    await refresh('agent')

    expect(FakeEventSource.instances).toHaveLength(2)
    expect(FakeEventSource.instances[1].url).toContain('token=tok2')
    expect(FakeEventSource.instances[0].closed).toBe(true) // 이전 연결 정리

    handle.close()
    expect(FakeEventSource.instances[1].closed).toBe(true)
  })

  it('operator refresh는 agent 스트림을 재오픈하지 않는다', async () => {
    setAccess('agent', 'a1')
    openEscalationStream(() => {})
    expect(FakeEventSource.instances).toHaveLength(1)

    globalThis.fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ access_token: 'op' }) })
    await refresh('operator')

    expect(FakeEventSource.instances).toHaveLength(1) // 변동 없음
  })
})
