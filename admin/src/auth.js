// 어드민 인증 클라이언트 (ADR-0013).
// access는 sessionStorage(단수명), refresh는 httpOnly 쿠키(JS가 못 읽음).
// authFetch가 401 시 1회 투명 refresh→재시도하고, 부팅 시 silent refresh로 access를 복구한다.

const BASE = import.meta.env.VITE_API_BASE || ''

const ACCESS_KEY = { operator: 'op_access', agent: 'agent_access' }
const REFRESH_PATH = {
  operator: '/api/operator/auth/refresh',
  agent: '/api/tenant/agents/auth/refresh',
}

// access 갱신 구독자(kind별). silent refresh로 토큰이 바뀌면 SSE 재오픈 등에 알린다.
const accessListeners = { operator: new Set(), agent: new Set() }

export function onAccessChange(kind, cb) {
  accessListeners[kind].add(cb)
  return () => accessListeners[kind].delete(cb)
}

function notifyAccessChange(kind) {
  for (const cb of accessListeners[kind]) cb()
}

export function getAccess(kind) {
  return sessionStorage.getItem(ACCESS_KEY[kind])
}
export function setAccess(kind, token) {
  sessionStorage.setItem(ACCESS_KEY[kind], token)
}
export function clearAccess(kind) {
  sessionStorage.removeItem(ACCESS_KEY[kind])
}

export async function refresh(kind) {
  const res = await fetch(`${BASE}${REFRESH_PATH[kind]}`, {
    method: 'POST',
    credentials: 'include', // refresh 쿠키 동봉
  })
  if (!res.ok) {
    clearAccess(kind)
    return false
  }
  const { access_token } = await res.json()
  setAccess(kind, access_token)
  notifyAccessChange(kind) // 새 토큰으로 갱신됨 → 구독자(SSE 등)에 통지
  return true
}

export async function authFetch(kind, path, opts = {}) {
  const send = () =>
    fetch(`${BASE}${path}`, {
      ...opts,
      credentials: 'include',
      headers: { ...(opts.headers || {}), Authorization: `Bearer ${getAccess(kind)}` },
    })

  let res = await send()
  if (res.status === 401 && (await refresh(kind))) {
    res = await send() // 새 access로 1회 재시도
  }
  return res
}

export async function bootSilentRefresh(kind) {
  if (getAccess(kind)) return true
  return refresh(kind)
}
