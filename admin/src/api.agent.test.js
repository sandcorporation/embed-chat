import { describe, it, expect, beforeEach, vi } from 'vitest'
import { tenantAgentLogin, getTenantConfig } from './api'
import { getAccess, setAccess } from './auth'

beforeEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe('tenantAgentLogin', () => {
  it('성공 시 access를 sessionStorage(agent)에 저장하고 credentials include로 호출한다', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true, json: async () => ({ access_token: 'agt' }),
    })
    globalThis.fetch = fetchMock

    await tenantAgentLogin('Acme', 'alice', 'pw')

    expect(getAccess('agent')).toBe('agt')
    expect(fetchMock.mock.calls[0][1].credentials).toBe('include')
  })
})

describe('getTenantConfig', () => {
  it('authFetch(agent) 경유로 agent access를 Authorization 헤더에 싣는다', async () => {
    setAccess('agent', 'agt2')
    const fetchMock = vi.fn().mockResolvedValueOnce({
      status: 200, ok: true, json: async () => ({}),
    })
    globalThis.fetch = fetchMock

    await getTenantConfig()

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer agt2')
  })
})
