// 챗 트랜스포트 경계 — ChatWidget이 SSE 생성·메시지 전송을 주입받아, 실제 백엔드 또는 mock으로
// 구동될 수 있게 한다(랜딩 데모는 mock으로 토큰 스트리밍을 연출). 기본 구현은 현재 동작 그대로.

export const API_BASE: string = import.meta.env.VITE_API_BASE || ''

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
