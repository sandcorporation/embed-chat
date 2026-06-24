import { useMemo } from 'react'
import ChatWidget from './components/ChatWidget'

// /chatbot/{slug}/ 경로에서 Tenant Slug를 추출한다 (EmbedToken 폐지, issue 85).
// 한글 slug(issue 187): percent-encoded path를 디코딩하고 NFC로 정규화한다 — 브라우저/OS가
// NFD(자모분리)로 줄 수 있어, 백엔드의 NFC 저장·iexact 조회와 일치시키려면 NFC가 필수.
export function resolveSlug(): string {
  const m = window.location.pathname.match(/\/chatbot\/([^/?#]+)/)
  return m ? decodeURIComponent(m[1]).normalize('NFC') : ''
}

// Visitor 식별: ?visitor_id= 명시값 우선, 없으면 위젯이 생성·localStorage에 지속하는
// Anonymous Visitor ID를 사용한다(세션을 넘어 이력·기억이 같은 브라우저에서 축적).
function resolveVisitorId(): string {
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
