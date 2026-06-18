import { useMemo } from 'react'
import ChatWidget from './components/ChatWidget'

// /chatbot/{slug}/ 경로에서 Tenant Slug를 추출한다 (EmbedToken 폐지, issue 85).
function resolveSlug() {
  const m = window.location.pathname.match(/\/chatbot\/([^/?#]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

// Visitor 식별: ?visitor_id= 명시값 우선, 없으면 위젯이 생성·localStorage에 지속하는
// Anonymous Visitor ID를 사용한다(세션을 넘어 이력·기억이 같은 브라우저에서 축적).
function resolveVisitorId() {
  const explicit = new URLSearchParams(window.location.search).get('visitor_id')
  if (explicit) return explicit

  const KEY = 'embed_chat_visitor_id'
  let vid = localStorage.getItem(KEY)
  if (!vid) {
    vid = crypto.randomUUID
      ? crypto.randomUUID()
      : `anon-${Math.random().toString(36).slice(2)}-${Date.now()}`
    localStorage.setItem(KEY, vid)
  }
  return vid
}

function App() {
  const slug = useMemo(resolveSlug, [])
  const visitorId = useMemo(resolveVisitorId, [])
  // 신원검증(opt-in)을 켠 Tenant는 ?hash=로 HMAC 검증 해시를 함께 넘긴다.
  const hash = useMemo(
    () => new URLSearchParams(window.location.search).get('hash') || '',
    []
  )

  if (!slug) {
    return (
      <div style={{ padding: '20px', color: '#e53e3e' }}>
        잘못된 챗봇 주소입니다.
      </div>
    )
  }

  return <ChatWidget slug={slug} visitorId={visitorId} hash={hash} />
}

export default App
