import { describe, it, expect, beforeEach, vi } from 'vitest'
import { operatorLogout, operatorLogoutAll, agentLogout, agentLogoutAll } from './api'
import { getAccess, setAccess } from './auth'

beforeEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe('operatorLogout (이 기기)', () => {
  it('서버 logout을 credentials include로 호출하고 access를 제거한다', async () => {
    setAccess('operator', 'a')
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({}) })
    globalThis.fetch = fetchMock

    await operatorLogout()

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/operator/auth/logout'),
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    )
    expect(getAccess('operator')).toBeNull()
  })
})

describe('operatorLogoutAll (전체)', () => {
  it('logout-all을 access 토큰과 함께 호출하고 access를 제거한다', async () => {
    setAccess('operator', 'tok')
    const fetchMock = vi.fn().mockResolvedValueOnce({ status: 200, ok: true, json: async () => ({}) })
    globalThis.fetch = fetchMock

    await operatorLogoutAll()

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/operator/auth/logout-all')
    expect(init.headers.Authorization).toBe('Bearer tok')
    expect(getAccess('operator')).toBeNull()
  })
})

describe('agent 로그아웃', () => {
  it('agentLogout은 서버 logout 후 agent access를 제거한다', async () => {
    setAccess('agent', 'x')
    globalThis.fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({}) })
    await agentLogout()
    expect(getAccess('agent')).toBeNull()
  })

  it('agentLogoutAll은 logout-all 후 agent access를 제거한다', async () => {
    setAccess('agent', 'y')
    globalThis.fetch = vi.fn().mockResolvedValueOnce({ status: 200, ok: true, json: async () => ({}) })
    await agentLogoutAll()
    expect(getAccess('agent')).toBeNull()
  })
})
