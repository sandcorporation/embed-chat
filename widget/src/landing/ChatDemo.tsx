import { useRef, useMemo } from 'react'
import ChatWidget from '../components/ChatWidget'
import type { ChatWidgetHandle } from '../components/ChatWidget'
import { createMockChatTransport, DEMO_SUGGESTIONS } from './mockChatTransport'

// Hero의 라이브 챗봇 데모 — 실제 ChatWidget을 mock 트랜스포트로 구동한다. 추천 칩 클릭은
// ChatWidget의 imperative send로 질문을 보내고, mock이 토큰 스트리밍으로 답한다.
export default function ChatDemo() {
  const widgetRef = useRef<ChatWidgetHandle>(null)
  const transport = useMemo(() => createMockChatTransport(), [])

  return (
    <div>
      <div className="chips" data-testid="chat-chips">
        {DEMO_SUGGESTIONS.map(q => (
          <button key={q} className="chip" onClick={() => widgetRef.current?.send(q)}>
            {q}
          </button>
        ))}
      </div>
      <div className="demo-box">
        <ChatWidget ref={widgetRef} slug="demo" visitorId="demo-visitor" transport={transport} />
      </div>
    </div>
  )
}
