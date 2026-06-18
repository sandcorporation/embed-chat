const BASE = import.meta.env.VITE_API_BASE || ''

function getHeaders(token) {
  const h = { 'Content-Type': 'application/json' }
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

// ── Operator ─────────────────────────────────────────────────────────────

export async function operatorLogin(username, password) {
  const res = await fetch(`${BASE}/api/operator/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) throw new Error('Invalid credentials')
  return res.json()
}

export async function listTenants(token) {
  const res = await fetch(`${BASE}/api/operator/tenants/`, { headers: getHeaders(token) })
  return res.json()
}

export async function createTenant(token, name) {
  const res = await fetch(`${BASE}/api/operator/tenants/`, {
    method: 'POST',
    headers: getHeaders(token),
    body: JSON.stringify({ name }),
  })
  return res.json()
}

export async function suspendTenant(token, id) {
  const res = await fetch(`${BASE}/api/operator/tenants/${id}/suspend`, {
    method: 'PATCH',
    headers: getHeaders(token),
  })
  return res.json()
}

export async function deleteTenant(token, id) {
  await fetch(`${BASE}/api/operator/tenants/${id}`, {
    method: 'DELETE',
    headers: getHeaders(token),
  })
}

// ── TenantAgent Auth ──────────────────────────────────────────────────────

export async function tenantAgentLogin(tenantName, username, password) {
  const res = await fetch(`${BASE}/api/tenant/agents/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tenant_name: tenantName, username, password }),
  })
  if (!res.ok) throw new Error('Invalid credentials')
  return res.json()
}

// ── Tenant Config ─────────────────────────────────────────────────────────

export async function getTenantConfig(agentToken) {
  const res = await fetch(`${BASE}/api/tenant/config/`, { headers: getHeaders(agentToken) })
  return res.json()
}

export async function updateTenantConfig(agentToken, data) {
  const res = await fetch(`${BASE}/api/tenant/config/`, {
    method: 'PATCH',
    headers: getHeaders(agentToken),
    body: JSON.stringify(data),
  })
  return res.json()
}

export async function updateTenantSlug(agentToken, slug) {
  const res = await fetch(`${BASE}/api/tenant/slug/`, {
    method: 'PATCH',
    headers: getHeaders(agentToken),
    body: JSON.stringify({ slug }),
  })
  if (!res.ok) throw new Error('slug 저장 실패 (형식·중복·예약어 확인)')
  return res.json()
}

export async function resetTenantKey(agentToken) {
  const res = await fetch(`${BASE}/api/tenant/reset-key`, {
    method: 'POST',
    headers: getHeaders(agentToken),
  })
  if (!res.ok) throw new Error('재발급 실패')
  return res.json()
}


// ── Documents ─────────────────────────────────────────────────────────────

export async function listDocuments(agentToken) {
  const res = await fetch(`${BASE}/api/tenant/documents/`, { headers: { Authorization: `Bearer ${agentToken}` } })
  return res.json()
}

export async function uploadDocument(agentToken, file, name) {
  const formData = new FormData()
  formData.append('file', file)
  if (name) formData.append('name', name)
  const res = await fetch(`${BASE}/api/tenant/documents/`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${agentToken}` },
    body: formData,
  })
  return res.json()
}

export async function updateDocument(agentToken, id, name) {
  const res = await fetch(`${BASE}/api/tenant/documents/${id}`, {
    method: 'PATCH',
    headers: getHeaders(agentToken),
    body: JSON.stringify({ name }),
  })
  return res.json()
}

export async function deleteDocument(agentToken, id) {
  await fetch(`${BASE}/api/tenant/documents/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${agentToken}` },
  })
}

export async function listDocumentChunks(agentToken, docId) {
  const res = await fetch(`${BASE}/api/tenant/documents/${docId}/chunks`, {
    headers: { Authorization: `Bearer ${agentToken}` },
  })
  return res.json()
}

export async function searchGraph(agentToken, q) {
  const res = await fetch(`${BASE}/api/tenant/documents/graph/search?q=${encodeURIComponent(q)}`, {
    headers: getHeaders(agentToken),
  })
  return res.json()
}

export async function graphNeighbors(agentToken, entity) {
  const res = await fetch(`${BASE}/api/tenant/documents/graph/neighbors?entity=${encodeURIComponent(entity)}`, {
    headers: getHeaders(agentToken),
  })
  return res.json()
}

export async function getGraphStatus(agentToken) {
  const res = await fetch(`${BASE}/api/tenant/documents/graph/status`, { headers: getHeaders(agentToken) })
  return res.json()
}

export async function rebuildGraph(agentToken) {
  const res = await fetch(`${BASE}/api/tenant/documents/graph/rebuild`, {
    method: 'POST',
    headers: getHeaders(agentToken),
  })
  return res.json()
}

// ── Visitors ──────────────────────────────────────────────────────────────

export async function listVisitors(agentToken, search) {
  const url = search
    ? `${BASE}/api/tenant/visitors/?search=${encodeURIComponent(search)}`
    : `${BASE}/api/tenant/visitors/`
  const res = await fetch(url, { headers: getHeaders(agentToken) })
  return res.json()
}

export async function listVisitorSessions(agentToken, visitorId) {
  const res = await fetch(`${BASE}/api/tenant/visitors/${visitorId}/sessions/`, {
    headers: getHeaders(agentToken),
  })
  return res.json()
}

export async function getSessionMessages(agentToken, sessionId) {
  const res = await fetch(`${BASE}/api/tenant/sessions/${sessionId}/messages/`, {
    headers: getHeaders(agentToken),
  })
  return res.json()
}

export async function getSessionCheckpoint(agentToken, sessionId) {
  const res = await fetch(`${BASE}/api/tenant/sessions/${sessionId}/checkpoint`, {
    headers: getHeaders(agentToken),
  })
  if (res.status === 404) return null
  return res.json()
}

// ── Memory ────────────────────────────────────────────────────────────────

export async function listMemories(agentToken, visitorId) {
  const res = await fetch(`${BASE}/api/tenant/visitors/${visitorId}/memory/`, {
    headers: getHeaders(agentToken),
  })
  return res.json()
}

export async function updateMemory(agentToken, visitorId, memoryId, data) {
  const res = await fetch(`${BASE}/api/tenant/visitors/${visitorId}/memory/${memoryId}`, {
    method: 'PATCH',
    headers: getHeaders(agentToken),
    body: JSON.stringify(data),
  })
  return res.json()
}

export async function deleteMemory(agentToken, visitorId, memoryId) {
  await fetch(`${BASE}/api/tenant/visitors/${visitorId}/memory/${memoryId}`, {
    method: 'DELETE',
    headers: getHeaders(agentToken),
  })
}

// ── TenantAgent Management ────────────────────────────────────────────────

export async function listAgents(agentToken) {
  const res = await fetch(`${BASE}/api/tenant/agents/`, { headers: getHeaders(agentToken) })
  return res.json()
}

export async function createAgent(agentToken, username) {
  const res = await fetch(`${BASE}/api/tenant/agents/`, {
    method: 'POST',
    headers: getHeaders(agentToken),
    body: JSON.stringify({ username }),
  })
  return res.json()
}

export async function deactivateAgent(agentToken, agentId) {
  const res = await fetch(`${BASE}/api/tenant/agents/${agentId}/deactivate`, {
    method: 'PATCH',
    headers: getHeaders(agentToken),
  })
  return res.json()
}

export async function changePassword(agentToken, currentPassword, newPassword) {
  const res = await fetch(`${BASE}/api/tenant/agents/me/change-password`, {
    method: 'POST',
    headers: getHeaders(agentToken),
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
  if (!res.ok) throw new Error('현재 비밀번호가 올바르지 않습니다.')
  return res.json()
}

// ── Escalations (HITL) ────────────────────────────────────────────────────

export async function listEscalations(agentToken) {
  const res = await fetch(`${BASE}/api/tenant/escalations/`, { headers: getHeaders(agentToken) })
  return res.json()
}

export async function claimEscalation(agentToken, escalationId) {
  const res = await fetch(`${BASE}/api/tenant/escalations/${escalationId}/claim`, {
    method: 'POST',
    headers: getHeaders(agentToken),
  })
  return res
}

export async function sendEscalationMessage(agentToken, escalationId, content) {
  const res = await fetch(`${BASE}/api/tenant/escalations/${escalationId}/message`, {
    method: 'POST',
    headers: getHeaders(agentToken),
    body: JSON.stringify({ content }),
  })
  return res.json()
}

export async function resolveEscalation(agentToken, escalationId) {
  const res = await fetch(`${BASE}/api/tenant/escalations/${escalationId}/resolve`, {
    method: 'POST',
    headers: getHeaders(agentToken),
  })
  return res.json()
}

export async function sendTypingIndicator(agentToken, escalationId) {
  await fetch(`${BASE}/api/tenant/escalations/${escalationId}/typing`, {
    method: 'POST',
    headers: getHeaders(agentToken),
  })
}

export async function getEscalationMessages(agentToken, escalationId) {
  const res = await fetch(`${BASE}/api/tenant/escalations/${escalationId}/messages`, {
    headers: getHeaders(agentToken),
  })
  return res.json()
}

export function openEscalationStream(agentToken, onEvent) {
  const es = new EventSource(`${BASE}/api/tenant/escalations/stream?token=${agentToken}`)
  es.onmessage = (e) => onEvent(JSON.parse(e.data))
  es.addEventListener('hitl_new', (e) => onEvent({ ...JSON.parse(e.data), type: 'hitl_new' }))
  es.addEventListener('hitl_claimed', (e) => onEvent({ ...JSON.parse(e.data), type: 'hitl_claimed' }))
  es.addEventListener('hitl_resolved', (e) => onEvent({ ...JSON.parse(e.data), type: 'hitl_resolved' }))
  es.addEventListener('visitor_message', (e) => onEvent({ ...JSON.parse(e.data), type: 'visitor_message' }))
  return es
}
