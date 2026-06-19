import { describe, it, expect, beforeEach, vi } from 'vitest'
import { operatorLogin, listTenants } from './api'
import { getAccess, setAccess } from './auth'

beforeEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe('operatorLogin', () => {
  it('성공 시 access를 sessionStorage에 저장하고 refresh 쿠키를 위해 credentials include로 호출한다', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true, json: async () => ({ access_token: 'acc' }),
    })
    globalThis.fetch = fetchMock

    await operatorLogin('admin', 'pw')

    expect(getAccess('operator')).toBe('acc')
    expect(fetchMock.mock.calls[0][1].credentials).toBe('include')
  })
})

describe('listTenants', () => {
  it('authFetch 경유로 access 토큰을 Authorization 헤더에 싣는다', async () => {
    setAccess('operator', 'acc2')
    const fetchMock = vi.fn().mockResolvedValueOnce({
      status: 200, ok: true, json: async () => [],
    })
    globalThis.fetch = fetchMock

    await listTenants()

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer acc2')
  })
})
