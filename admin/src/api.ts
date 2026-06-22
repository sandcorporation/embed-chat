// admin HTTP facade (ADR-0014). CRUD는 전부 orval 생성 클라이언트(→ mutator)를 거친다.
// 손작성으로 남는 것: login/logout의 토큰 부수효과 + SSE(openEscalationStream).
// 이 facade는 친근한 함수명 + .data 언랩 + 일부 특수 계약(409/404/친절 에러)만 담당한다.
import { setAccess, clearAccess, getAccess, onAccessChange } from './auth'
import { HttpError } from './mutator'

import {
  appsTenantsApiLogin,
  appsTenantsApiOperatorLogout,
  appsTenantsApiOperatorLogoutAll,
  appsTenantsApiListTenants,
  appsTenantsApiCreateTenant,
  appsTenantsApiDeleteTenant,
  appsTenantsApiSuspendTenant,
} from './generated/endpoints/operator/operator'
import {
  appsTenantsApiGetConfig,
  appsTenantsApiUpdateConfig,
  appsTenantsApiResetTenantKey,
  appsTenantsApiUpdateSlug,
  appsTenantsApiProviderModels,
} from './generated/endpoints/tenant/tenant'
import {
  appsTenantsApiAgentLogin,
  appsTenantsApiAgentLogout,
  appsTenantsApiAgentLogoutAll,
  appsTenantsApiListAgents,
  appsTenantsApiCreateAgent,
  appsTenantsApiDeactivateAgent,
  appsTenantsApiChangePassword,
} from './generated/endpoints/tenant-agents/tenant-agents'
import {
  appsRagApiListDocuments,
  appsRagApiUploadDocument,
  appsRagApiUpdateDocument,
  appsRagApiDeleteDocument,
  appsRagApiListChunks,
  appsRagApiGraphSearch,
  appsRagApiGraphNeighbors,
  appsRagApiGraphStatus,
  appsRagApiRebuildGraph,
} from './generated/endpoints/rag/rag'
import {
  appsMemoryApiListVisitors,
  appsMemoryApiListVisitorSessions,
  appsMemoryApiListMemories,
  appsMemoryApiUpdateMemory,
  appsMemoryApiDeleteMemoryEntry,
} from './generated/endpoints/memory/memory'
import {
  appsMemoryApiGetSessionMessages,
  appsMemoryApiGetSessionCheckpoint,
  appsMemoryApiListSessions,
  appsMemoryApiTakeoverSession,
} from './generated/endpoints/sessions/sessions'
import {
  appsEscalationApiListEscalations,
  appsEscalationApiClaimEscalation,
  appsEscalationApiSendMessage,
  appsEscalationApiGetEscalationMessages,
  appsEscalationApiResolveEscalation,
  appsEscalationApiSendTypingIndicator,
} from './generated/endpoints/escalations/escalations'

const BASE: string = import.meta.env.VITE_API_BASE || ''

// ── Operator ─────────────────────────────────────────────────────────────

export async function operatorLogin(username: string, password: string) {
  const data = (await appsTenantsApiLogin({ username, password })).data as { access_token: string }
  setAccess('operator', data.access_token)
  return data
}
export async function operatorLogout() {
  await appsTenantsApiOperatorLogout()
  clearAccess('operator')
}
export async function operatorLogoutAll() {
  await appsTenantsApiOperatorLogoutAll()
  clearAccess('operator')
}
export async function listTenants() {
  return (await appsTenantsApiListTenants()).data
}
export async function createTenant(name: string) {
  return (await appsTenantsApiCreateTenant({ name })).data
}
export async function suspendTenant(id: string) {
  return (await appsTenantsApiSuspendTenant(id)).data
}
export async function deleteTenant(id: string) {
  await appsTenantsApiDeleteTenant(id)
}

// ── TenantAgent auth + management ─────────────────────────────────────────

export async function tenantAgentLogin(tenantName: string, username: string, password: string) {
  const data = (await appsTenantsApiAgentLogin({ tenant_name: tenantName, username, password })).data as { access_token: string }
  setAccess('agent', data.access_token)
  return data
}
export async function agentLogout() {
  await appsTenantsApiAgentLogout()
  clearAccess('agent')
}
export async function agentLogoutAll() {
  await appsTenantsApiAgentLogoutAll()
  clearAccess('agent')
}
export async function listAgents() {
  return (await appsTenantsApiListAgents()).data
}
export async function createAgent(username: string) {
  return (await appsTenantsApiCreateAgent({ username })).data
}
export async function deactivateAgent(agentId: string) {
  return (await appsTenantsApiDeactivateAgent(agentId)).data
}
export async function changePassword(currentPassword: string, newPassword: string) {
  try {
    return (await appsTenantsApiChangePassword({ current_password: currentPassword, new_password: newPassword })).data
  } catch (e) {
    throw new Error('현재 비밀번호가 올바르지 않습니다.')
  }
}

// ── Tenant Config ─────────────────────────────────────────────────────────

export async function getTenantConfig() {
  return (await appsTenantsApiGetConfig()).data
}
export async function updateTenantConfig(data: any) {
  return (await appsTenantsApiUpdateConfig(data)).data
}
export async function updateTenantSlug(slug: string) {
  try {
    return (await appsTenantsApiUpdateSlug({ slug })).data
  } catch (e) {
    throw new Error('slug 저장 실패 (형식·중복·예약어 확인)')
  }
}
export async function resetTenantKey() {
  try {
    return (await appsTenantsApiResetTenantKey()).data
  } catch (e) {
    throw new Error('재발급 실패')
  }
}

// provider의 사용가능 모델 목록을 폼 현재 값으로 조회한다(어드민 "모델 불러오기").
// 마스크 키(********)는 백엔드가 저장 키로 대체한다. 실패 시 throw(키/URL 오류).
export async function fetchProviderModels(
  kind: 'llm' | 'embed' | 'ocr',
  providerType: string,
  baseUrl: string,
  apiKey: string,
  model: string,
): Promise<string[]> {
  const res = await appsTenantsApiProviderModels({
    kind, type: providerType, base_url: baseUrl, api_key: apiKey, model,
  })
  return (res.data as { models: string[] }).models
}

// ── Documents / Graph ──────────────────────────────────────────────────────

export async function listDocuments() {
  return (await appsRagApiListDocuments()).data
}
export async function uploadDocument(file: File, name?: string) {
  return (await appsRagApiUploadDocument({ file, name })).data
}
export async function updateDocument(id: string, name: string) {
  return (await appsRagApiUpdateDocument(id, { name })).data
}
export async function deleteDocument(id: string) {
  await appsRagApiDeleteDocument(id)
}
export async function listDocumentChunks(docId: string) {
  return (await appsRagApiListChunks(docId)).data
}
export async function searchGraph(q: string) {
  return (await appsRagApiGraphSearch({ q })).data
}
export async function graphNeighbors(entity: string) {
  return (await appsRagApiGraphNeighbors({ entity })).data
}
export async function getGraphStatus() {
  return (await appsRagApiGraphStatus()).data
}
export async function rebuildGraph() {
  return (await appsRagApiRebuildGraph()).data
}

// ── Visitors / Memory / Sessions ───────────────────────────────────────────

export async function listVisitors(search?: string) {
  return (await appsMemoryApiListVisitors(search ? { search } : undefined)).data
}
export async function listVisitorSessions(visitorId: string) {
  return (await appsMemoryApiListVisitorSessions(visitorId)).data
}
export async function getSessionMessages(sessionId: string) {
  return (await appsMemoryApiGetSessionMessages(sessionId)).data
}
// 세션 콘솔: 전체 세션(escalation→활성→나머지) 목록(issue 139).
export async function listSessions(limit = 50, offset = 0) {
  return (await appsMemoryApiListSessions({ limit, offset })).data
}
// 임의 세션 takeover — 자동-claimed escalation 생성. 409(다른 상담원 점유) 정규화(issue 140).
export async function takeoverSession(
  sessionId: string,
): Promise<{ ok: boolean; status: number; escalation_id?: string }> {
  try {
    const r = await appsMemoryApiTakeoverSession(sessionId)
    return { ok: true, status: r.status, escalation_id: (r.data as { escalation_id: string }).escalation_id }
  } catch (e) {
    if (e instanceof HttpError) return { ok: false, status: e.status }
    throw e
  }
}
export async function getSessionCheckpoint(sessionId: string) {
  try {
    return (await appsMemoryApiGetSessionCheckpoint(sessionId)).data
  } catch (e) {
    if (e instanceof HttpError && e.status === 404) return null
    throw e
  }
}
export async function listMemories(visitorId: string) {
  return (await appsMemoryApiListMemories(visitorId)).data
}
export async function updateMemory(visitorId: string, memoryId: string, data: { key: string; value: string }) {
  return (await appsMemoryApiUpdateMemory(visitorId, memoryId, data)).data
}
export async function deleteMemory(visitorId: string, memoryId: string) {
  await appsMemoryApiDeleteMemoryEntry(visitorId, memoryId)
}

// ── Escalations (HITL) ────────────────────────────────────────────────────

export async function listEscalations() {
  return (await appsEscalationApiListEscalations()).data
}
// claim은 409(이미 수락됨) 분기가 있어 status/ok로 정규화해 반환
export async function claimEscalation(escalationId: string): Promise<{ status: number; ok: boolean }> {
  try {
    const r = await appsEscalationApiClaimEscalation(escalationId)
    return { status: r.status, ok: true }
  } catch (e) {
    if (e instanceof HttpError) return { status: e.status, ok: false }
    throw e
  }
}
export async function sendEscalationMessage(escalationId: string, content: string) {
  return (await appsEscalationApiSendMessage(escalationId, { content })).data
}
export async function resolveEscalation(escalationId: string) {
  return (await appsEscalationApiResolveEscalation(escalationId)).data
}
export async function sendTypingIndicator(escalationId: string) {
  await appsEscalationApiSendTypingIndicator(escalationId)
}
export async function getEscalationMessages(escalationId: string) {
  return (await appsEscalationApiGetEscalationMessages(escalationId)).data
}

// ── SSE (손작성 — OpenAPI 모델링 불가) ──────────────────────────────────────
export interface StreamHandle {
  close: () => void
}
export function openEscalationStream(onEvent: (event: any) => void): StreamHandle {
  let es: EventSource | null = null
  const connect = () => {
    if (es) es.close()
    es = new EventSource(`${BASE}/api/tenant/escalations/stream?token=${getAccess('agent')}`)
    es.onmessage = (e) => onEvent(JSON.parse(e.data))
    es.addEventListener('hitl_new', (e) => onEvent({ ...JSON.parse((e as MessageEvent).data), type: 'hitl_new' }))
    es.addEventListener('hitl_claimed', (e) => onEvent({ ...JSON.parse((e as MessageEvent).data), type: 'hitl_claimed' }))
    es.addEventListener('hitl_resolved', (e) => onEvent({ ...JSON.parse((e as MessageEvent).data), type: 'hitl_resolved' }))
    es.addEventListener('visitor_message', (e) => onEvent({ ...JSON.parse((e as MessageEvent).data), type: 'visitor_message' }))
    // presence delta(issue 138) — 세션 콘솔 활성 계층 라이브 갱신
    es.addEventListener('session_connected', (e) => onEvent({ ...JSON.parse((e as MessageEvent).data), type: 'session_connected' }))
    es.addEventListener('session_disconnected', (e) => onEvent({ ...JSON.parse((e as MessageEvent).data), type: 'session_disconnected' }))
  }
  connect()
  const unsubscribe = onAccessChange('agent', connect)
  return {
    close() {
      if (es) es.close()
      unsubscribe()
    },
  }
}
