// 챗 트랜스포트 경계 — ChatWidget이 SSE 생성·메시지 전송을 주입받아, 실제 백엔드 또는 mock으로
// 구동될 수 있게 한다(랜딩 데모는 mock으로 토큰 스트리밍을 연출). 기본 구현은 현재 동작 그대로.

export const API_BASE: string = import.meta.env.VITE_API_BASE || ''

export type ResolveResult = 'valid' | 'notfound' | 'error'

/** 공개 위젯 진입 가드 — slug가 활성 Tenant로 해석되는지 확인(렌더 전 호출).
 *  200=valid, 404=notfound(존재하지 않는 챗봇), 그 외/네트워크 오류=error(일시적). */
export async function resolveTenant(slug: string): Promise<ResolveResult> {
  try {
    const res = await fetch(`${API_BASE}/api/chat/resolve?slug=${encodeURIComponent(slug)}`)
    if (res.ok) return 'valid'
    if (res.status === 404) return 'notfound'
    return 'error'
  } catch {
    return 'error'
  }
}

/** ChatWidget이 쓰는 최소 EventSource 표면(실제 EventSource·mock 둘 다 만족). */
export interface EventSourceLike {
  addEventListener(type: string, listener: (e: { data: string }) => void): void
  close(): void
  onerror: ((ev: unknown) => void) | null
}

export interface ChatTransport {
  createEventSource(url: string): EventSourceLike
  postMessage(sessionId: string, content: string): Promise<void>
}

/** 실제 백엔드 트랜스포트(기본값) — SSE 연결 + 메시지 POST. */
export const realTransport: ChatTransport = {
  createEventSource: (url) => new EventSource(url) as unknown as EventSourceLike,
  postMessage: async (sessionId, content) => {
    await fetch(`${API_BASE}/api/chat/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, content }),
    })
  },
}
