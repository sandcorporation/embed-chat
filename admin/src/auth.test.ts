import { describe, it, expect, beforeEach, vi } from 'vitest'
import { authFetch, refresh, bootSilentRefresh, getAccess, setAccess, clearAccess } from './auth'

beforeEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe('authFetch — 401 투명 refresh + 재시도', () => {
  it('401이면 refresh로 새 access를 받아 원요청을 재시도한다', async () => {
    setAccess('operator', 'old-access')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ status: 401, ok: false })                                  // 원요청 401
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ access_token: 'new-access' }) }) // refresh
      .mockResolvedValueOnce({ status: 200, ok: true })                                    // 재시도
    globalThis.fetch = fetchMock

    const res = await authFetch('operator', '/api/operator/tenants/')

    expect(res.status).toBe(200)
    // 재시도 요청은 새 access를 달고 나간다
    const retryInit = fetchMock.mock.calls[2][1]
    expect(retryInit.headers.Authorization).toBe('Bearer new-access')
    expect(getAccess('operator')).toBe('new-access')
  })
})

describe('bootSilentRefresh', () => {
  it('access가 없으면 refresh를 호출해 복구한다', async () => {
    clearAccess('operator')
    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true, status: 200, json: async () => ({ access_token: 'boot-access' }),
    })
    globalThis.fetch = fetchMock

    await bootSilentRefresh('operator')

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/operator/auth/refresh'),
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    )
    expect(getAccess('operator')).toBe('boot-access')
  })
})

describe('refresh 실패', () => {
  it('refresh가 401이면 access를 제거하고 false를 반환한다', async () => {
    setAccess('operator', 'stale')
    globalThis.fetch = vi.fn().mockResolvedValueOnce({ ok: false, status: 401 })

    const ok = await refresh('operator')

    expect(ok).toBe(false)
    expect(getAccess('operator')).toBeNull()
  })
})
