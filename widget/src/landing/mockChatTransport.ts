import type { ChatTransport, EventSourceLike } from '../transport'

// 랜딩 데모용 mock 트랜스포트 — 실제 ChatWidget을 백엔드 없이 구동한다. postMessage 시 질문에 맞는
// 스크립트 답변을 토큰 델타로 흘려(setInterval) 실시간 스트리밍 + 마크다운 렌더를 그대로 쇼케이스.

class MockEventSource implements EventSourceLike {
  private listeners: Record<string, ((e: { data: string }) => void)[]> = {}
  onerror: ((ev: unknown) => void) | null = null
  addEventListener(type: string, fn: (e: { data: string }) => void) {
    (this.listeners[type] ||= []).push(fn)
  }
  close() {}
  emit(type: string, data: unknown) {
    (this.listeners[type] || []).forEach(fn => fn({ data: JSON.stringify(data) }))
  }
}

interface ScriptedAnswer { match: RegExp; answer: string }

const ANSWERS: ScriptedAnswer[] = [
  { match: /지식\s*그래프|graph|rag/i, answer: '**지식그래프 기반 RAG**예요. 문서를 Entity·관계로 구조화해서, 단순 벡터 검색보다 정확한 근거로 답합니다.\n\n- 추출된 Entity·관계를 그래프로 저장\n- 질문에 맞는 서브그래프 + 원문을 근거로 응답' },
  { match: /스트리밍|streaming|실시간/i, answer: '답변은 **토큰 단위로 실시간** 흘러나와요. 지금 보시는 것처럼 타이핑되듯 렌더되고, `마크다운`도 그대로 보여집니다.' },
  { match: /상담원|hitl|사람|전환/i, answer: 'AI가 불확실하거나 방문자가 원하면 **사람 상담원으로 전환**합니다. 운영자 콘솔에서 실시간으로 이어받을 수 있어요.' },
  { match: /위젯|widget|삽입|embed|어떻게/i, answer: '한 줄 스니펫으로 어떤 사이트에도 **임베드**됩니다. 지금 이 데모 챗봇이 바로 그 위젯이에요 🙂' },
  { match: /가격|요금|price|cost/i, answer: '요금은 문의해 주세요 — 아래 **Contact**의 이메일/전화로 연락 주시면 안내드립니다.' },
]
const DEFAULT_ANSWER = '이건 **데모**라 미리 준비된 답변을 보여드려요 🙂\n\n"지식그래프", "스트리밍", "상담원 전환", "위젯 삽입" 같은 걸 물어보세요!'

function toChunks(text: string): string[] {
  const out: string[] = []
  for (let i = 0; i < text.length; i += 3) out.push(text.slice(i, i + 3))  // 3글자 단위 델타
  return out
}

export const DEMO_SUGGESTIONS = ['지식그래프가 뭐죠?', '실시간 스트리밍이 뭔가요?', '상담원 전환도 되나요?', '어떻게 삽입하나요?']

export interface MockOptions { stepMs?: number }

export function createMockChatTransport(opts: MockOptions = {}): ChatTransport {
  const stepMs = opts.stepMs ?? 35
  let es: MockEventSource | null = null
  let timer: ReturnType<typeof setInterval> | undefined
  return {
    createEventSource: () => {
      es = new MockEventSource()
      const cur = es
      // 실제 EventSource처럼 비동기로 connected 발화(리스너가 붙은 뒤).
      setTimeout(() => cur.emit('connected', {
        session_id: 'demo',
        welcome_message: '안녕하세요! 무엇이든 물어보세요 👋 (예: 지식그래프가 뭐죠?)',
      }), 0)
      return es
    },
    postMessage: async (_sessionId, content) => {
      const cur = es
      if (!cur) return
      const answer = ANSWERS.find(a => a.match.test(content))?.answer ?? DEFAULT_ANSWER
      const chunks = toChunks(answer)
      let i = 0
      clearInterval(timer)
      timer = setInterval(() => {
        if (i < chunks.length) cur.emit('token', { content: chunks[i++] })
        else { clearInterval(timer); cur.emit('done', {}) }
      }, stepMs)
    },
  }
}
