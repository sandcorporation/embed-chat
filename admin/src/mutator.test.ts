import { describe, it, expect, beforeEach, vi } from 'vitest'
import { customInstance } from './mutator'
import { setAccess, getAccess } from './auth'

beforeEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe('customInstance — kind 판정 + bearer + credentials', () => {
  it('operator URL은 operator access를 Bearer로 싣고 파싱된 데이터를 반환한다', async () => {
    setAccess('operator', 'op-tok')
    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true, status: 200, text: async () => JSON.stringify({ ok: 1 }),
    })
    globalThis.fetch = fetchMock

    const data = await customInstance({ url: '/api/operator/tenants/', method: 'GET' })

    expect(data).toEqual({ ok: 1 })
    const init = fetchMock.mock.calls[0][1]
    expect(init.headers.Authorization).toBe('Bearer op-tok')
    expect(init.credentials).toBe('include')
  })

  it('agent URL은 agent access를 싣는다', async () => {
    setAccess('agent', 'ag-tok')
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, status: 200, text: async () => '{}' })
    globalThis.fetch = fetchMock

    await customInstance({ url: '/api/tenant/config/', method: 'GET' })

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer ag-tok')
  })

  it('POST data를 JSON 직렬화하고 Content-Type을 단다', async () => {
    setAccess('agent', 't')
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, status: 200, text: async () => '{}' })
    globalThis.fetch = fetchMock

    await customInstance({ url: '/api/tenant/config/', method: 'PATCH', data: { a: 1 } })

    const init = fetchMock.mock.calls[0][1]
    expect(init.body).toBe(JSON.stringify({ a: 1 }))
    expect(init.headers['Content-Type']).toBe('application/json')
  })
})

describe('customInstance — 401 투명 refresh', () => {
  it('401이면 refresh 후 새 토큰으로 재시도하고 데이터를 반환한다', async () => {
    setAccess('agent', 'old')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => '' })                       // 원요청 401
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ access_token: 'new' }) })  // refresh
      .mockResolvedValueOnce({ ok: true, status: 200, text: async () => JSON.stringify({ v: 2 }) })    // 재시도
    globalThis.fetch = fetchMock

    const data = await customInstance({ url: '/api/tenant/config/', method: 'GET' })

    expect(data).toEqual({ v: 2 })
    expect(getAccess('agent')).toBe('new')
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe('Bearer new')
  })

  it('refresh가 실패하면 throw한다', async () => {
    setAccess('agent', 'x')
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => '' })  // 원요청 401
      .mockResolvedValueOnce({ ok: false, status: 401 })                         // refresh 실패
    await expect(customInstance({ url: '/api/tenant/config/', method: 'GET' })).rejects.toThrow()
  })
})

describe('customInstance — 비-2xx throw', () => {
  it('재시도 후에도 비-2xx면 status를 담아 throw한다', async () => {
    setAccess('agent', 'x')
    globalThis.fetch = vi.fn().mockResolvedValueOnce({ ok: false, status: 500, text: async () => 'boom' })
    await expect(customInstance({ url: '/api/tenant/config/', method: 'GET' }))
      .rejects.toMatchObject({ status: 500 })
  })
})
