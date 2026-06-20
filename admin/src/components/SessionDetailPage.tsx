import { useParams, useNavigate } from 'react-router-dom'
import SessionDetail from './SessionDetail'

// /tenant/sessions/:sessionId 라우트 래퍼 — 세션 상세를 URL로 딥링크/공유 가능하게 한다(ADR-0017).
export default function SessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  if (!sessionId) return null
  return <SessionDetail sessionId={sessionId} onBack={() => navigate(-1)} />
}
