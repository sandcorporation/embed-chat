import { authFetch, setAccess, getAccess } from './auth'

const BASE = import.meta.env.VITE_API_BASE || ''

const JSON_HEADERS = { 'Content-Type': 'application/json' }

// ── Operator ─────────────────────────────────────────────────────────────

export async function operatorLogin(username, password) {
  const res = await fetch(`${BASE}/api/operator/auth/login`, {
    method: 'POST',
    credentials: 'include', // 서버가 내려주는 refresh 쿠키 수신
    headers: JSON_HEADERS,
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) throw new Error('Invalid credentials')
  const data = await res.json()
  setAccess('operator', data.access_token)
  return data
}

export async function listTenants() {
  const res = await authFetch('operator', '/api/operator/tenants/')
  return res.json()
}

export async function createTenant(name) {
  const res = await authFetch('operator', '/api/operator/tenants/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ name }),
  })
  return res.json()
}

export async function suspendTenant(id) {
  const res = await authFetch('operator', `/api/operator/tenants/${id}/suspend`, {
    method: 'PATCH',
  })
  return res.json()
}

export async function deleteTenant(id) {
  await authFetch('operator', `/api/operator/tenants/${id}`, { method: 'DELETE' })
}

// ── TenantAgent Auth ──────────────────────────────────────────────────────

export async function tenantAgentLogin(tenantName, username, password) {
  const res = await fetch(`${BASE}/api/tenant/agents/auth/login`, {
    method: 'POST',
    credentials: 'include', // 서버가 내려주는 refresh 쿠키 수신
    headers: JSON_HEADERS,
    body: JSON.stringify({ tenant_name: tenantName, username, password }),
  })
  if (!res.ok) throw new Error('Invalid credentials')
  const data = await res.json()
  setAccess('agent', data.access_token)
  return data
}

// ── Tenant Config ─────────────────────────────────────────────────────────

export async function getTenantConfig() {
  const res = await authFetch('agent', '/api/tenant/config/')
  return res.json()
}

export async function updateTenantConfig(data) {
  const res = await authFetch('agent', '/api/tenant/config/', {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  })
  return res.json()
}

export async function updateTenantSlug(slug) {
  const res = await authFetch('agent', '/api/tenant/slug/', {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify({ slug }),
  })
  if (!res.ok) throw new Error('slug 저장 실패 (형식·중복·예약어 확인)')
  return res.json()
}

export async function resetTenantKey() {
  const res = await authFetch('agent', '/api/tenant/reset-key', { method: 'POST' })
  if (!res.ok) throw new Error('재발급 실패')
  return res.json()
}


// ── Documents ─────────────────────────────────────────────────────────────

export async function listDocuments() {
  const res = await authFetch('agent', '/api/tenant/documents/')
  return res.json()
}

export async function uploadDocument(file, name) {
  const formData = new FormData()
  formData.append('file', file)
  if (name) formData.append('name', name)
  const res = await authFetch('agent', '/api/tenant/documents/', {
    method: 'POST',
    body: formData, // Content-Type은 브라우저가 multipart boundary로 설정
  })
  return res.json()
}

export async function updateDocument(id, name) {
  const res = await authFetch('agent', `/api/tenant/documents/${id}`, {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify({ name }),
  })
  return res.json()
}

export async function deleteDocument(id) {
  await authFetch('agent', `/api/tenant/documents/${id}`, { method: 'DELETE' })
}

export async function listDocumentChunks(docId) {
  const res = await authFetch('agent', `/api/tenant/documents/${docId}/chunks`)
  return res.json()
}

export async function searchGraph(q) {
  const res = await authFetch('agent', `/api/tenant/documents/graph/search?q=${encodeURIComponent(q)}`)
  return res.json()
}

export async function graphNeighbors(entity) {
  const res = await authFetch('agent', `/api/tenant/documents/graph/neighbors?entity=${encodeURIComponent(entity)}`)
  return res.json()
}

export async function getGraphStatus() {
  const res = await authFetch('agent', '/api/tenant/documents/graph/status')
  return res.json()
}

export async function rebuildGraph() {
  const res = await authFetch('agent', '/api/tenant/documents/graph/rebuild', { method: 'POST' })
  return res.json()
}

// ── Visitors ──────────────────────────────────────────────────────────────

export async function listVisitors(search) {
  const url = search
    ? `/api/tenant/visitors/?search=${encodeURIComponent(search)}`
    : '/api/tenant/visitors/'
  const res = await authFetch('agent', url)
  return res.json()
}

export async function listVisitorSessions(visitorId) {
  const res = await authFetch('agent', `/api/tenant/visitors/${visitorId}/sessions/`)
  return res.json()
}

export async function getSessionMessages(sessionId) {
  const res = await authFetch('agent', `/api/tenant/sessions/${sessionId}/messages/`)
  return res.json()
}

export async function getSessionCheckpoint(sessionId) {
  const res = await authFetch('agent', `/api/tenant/sessions/${sessionId}/checkpoint`)
  if (res.status === 404) return null
  return res.json()
}

// ── Memory ────────────────────────────────────────────────────────────────

export async function listMemories(visitorId) {
  const res = await authFetch('agent', `/api/tenant/visitors/${visitorId}/memory/`)
  return res.json()
}

export async function updateMemory(visitorId, memoryId, data) {
  const res = await authFetch('agent', `/api/tenant/visitors/${visitorId}/memory/${memoryId}`, {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  })
  return res.json()
}

export async function deleteMemory(visitorId, memoryId) {
  await authFetch('agent', `/api/tenant/visitors/${visitorId}/memory/${memoryId}`, { method: 'DELETE' })
}

// ── TenantAgent Management ────────────────────────────────────────────────

export async function listAgents() {
  const res = await authFetch('agent', '/api/tenant/agents/')
  return res.json()
}

export async function createAgent(username) {
  const res = await authFetch('agent', '/api/tenant/agents/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ username }),
  })
  return res.json()
}

export async function deactivateAgent(agentId) {
  const res = await authFetch('agent', `/api/tenant/agents/${agentId}/deactivate`, { method: 'PATCH' })
  return res.json()
}

export async function changePassword(currentPassword, newPassword) {
  const res = await authFetch('agent', '/api/tenant/agents/me/change-password', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
  if (!res.ok) throw new Error('현재 비밀번호가 올바르지 않습니다.')
  return res.json()
}

// ── Escalations (HITL) ────────────────────────────────────────────────────

export async function listEscalations() {
  const res = await authFetch('agent', '/api/tenant/escalations/')
  return res.json()
}

export async function claimEscalation(escalationId) {
  return authFetch('agent', `/api/tenant/escalations/${escalationId}/claim`, { method: 'POST' })
}

export async function sendEscalationMessage(escalationId, content) {
  const res = await authFetch('agent', `/api/tenant/escalations/${escalationId}/message`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ content }),
  })
  return res.json()
}

export async function resolveEscalation(escalationId) {
  const res = await authFetch('agent', `/api/tenant/escalations/${escalationId}/resolve`, { method: 'POST' })
  return res.json()
}

export async function sendTypingIndicator(escalationId) {
  await authFetch('agent', `/api/tenant/escalations/${escalationId}/typing`, { method: 'POST' })
}

export async function getEscalationMessages(escalationId) {
  const res = await authFetch('agent', `/api/tenant/escalations/${escalationId}/messages`)
  return res.json()
}

export function openEscalationStream(onEvent) {
  // SSE는 access를 쿼리로 전달(EventSource는 헤더 미지원). 단수명 access 만료 시
  // 재오픈은 issue 101에서 처리. 토큰은 sessionStorage에서 라이브로 읽는다.
  const es = new EventSource(`${BASE}/api/tenant/escalations/stream?token=${getAccess('agent')}`)
  es.onmessage = (e) => onEvent(JSON.parse(e.data))
  es.addEventListener('hitl_new', (e) => onEvent({ ...JSON.parse(e.data), type: 'hitl_new' }))
  es.addEventListener('hitl_claimed', (e) => onEvent({ ...JSON.parse(e.data), type: 'hitl_claimed' }))
  es.addEventListener('hitl_resolved', (e) => onEvent({ ...JSON.parse(e.data), type: 'hitl_resolved' }))
  es.addEventListener('visitor_message', (e) => onEvent({ ...JSON.parse(e.data), type: 'visitor_message' }))
  return es
}
