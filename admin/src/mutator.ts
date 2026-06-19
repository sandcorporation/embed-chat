// orval custom instance (ADR-0014). 생성된 모든 클라이언트 함수가 이걸 거친다.
// ADR-0013의 authFetch 로직을 흡수하되, URL 프리픽스로 kind를 판정한다.

import { AuthKind, getAccess, refresh } from './auth'

const BASE: string = import.meta.env.VITE_API_BASE || ''

export interface MutatorConfig {
  url: string
  method: string
  params?: Record<string, unknown>
  data?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
}

export class HttpError extends Error {
  constructor(public status: number, public url: string, public body?: unknown) {
    super(`HTTP ${status} ${url}`)
    this.name = 'HttpError'
  }
}

function kindForUrl(url: string): AuthKind {
  // 라우터 마운트와 일치: /api/operator/* → operator, 그 외(/api/tenant/*) → agent
  return url.startsWith('/api/operator') ? 'operator' : 'agent'
}

function buildUrl(url: string, params?: Record<string, unknown>): string {
  if (!params) return `${BASE}${url}`
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) qs.append(k, String(v))
  }
  const s = qs.toString()
  return `${BASE}${url}${s ? `?${s}` : ''}`
}

async function parseBody<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

export async function customInstance<T>(config: MutatorConfig): Promise<T> {
  const kind = kindForUrl(config.url)
  const fullUrl = buildUrl(config.url, config.params)
  const isForm = config.data instanceof FormData

  const send = (): Promise<Response> => {
    const headers: Record<string, string> = { ...(config.headers || {}) }
    const access = getAccess(kind)
    if (access) headers.Authorization = `Bearer ${access}`

    const init: RequestInit = {
      method: config.method,
      credentials: 'include', // refresh 쿠키 동봉
      headers,
      signal: config.signal,
    }
    if (config.data !== undefined) {
      if (isForm) {
        init.body = config.data as FormData // Content-Type은 브라우저가 multipart로 설정
      } else {
        init.body = JSON.stringify(config.data)
        headers['Content-Type'] = headers['Content-Type'] || 'application/json'
      }
    }
    return fetch(fullUrl, init)
  }

  let res = await send()
  if (res.status === 401 && (await refresh(kind))) {
    res = await send() // 새 access로 1회 재시도
  }
  if (!res.ok) {
    let body: unknown
    try {
      body = await parseBody<unknown>(res)
    } catch {
      body = undefined
    }
    throw new HttpError(res.status, fullUrl, body)
  }
  return parseBody<T>(res)
}

export default customInstance
