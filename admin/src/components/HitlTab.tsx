import { useState, useEffect, useRef, ChangeEvent } from 'react'
import { listEscalations, claimEscalation, sendEscalationMessage, resolveEscalation, openEscalationStream, sendTypingIndicator, getEscalationMessages } from '../api'
import type { StreamHandle } from '../api'
import { s } from '../styles'
import type { EscalationOut } from '../generated/model'

const STATUS_LABEL: Record<string, string> = { pending: '대기 중', claimed: '진행 중', resolved: '완료' }
const STATUS_COLOR: Record<string, string> = { pending: '#e53e3e', claimed: '#d69e2e', resolved: '#38a169' }

const ROLE_LABEL: Record<string, string> = { user: 'Visitor', assistant: 'AI', human_agent: '상담원' }
const ROLE_ALIGN: Record<string, string> = { user: 'flex-start', assistant: 'flex-end', human_agent: 'flex-end' }
const ROLE_BG: Record<string, string> = { user: '#edf2f7', assistant: '#ebf8ff', human_agent: '#f0fff4' }

// API 메시지(EscalationMessageOut)와 로컬 추가 메시지(id 없음)를 함께 담는다.
type ChatMsg = { id?: string; role: string; content: string; created_at?: string }

function ChatHistory({ messages }: { messages: ChatMsg[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (!messages.length) return (
    <p style={{ fontSize: 12, color: '#a0aec0', textAlign: 'center', padding: '8px 0' }}>대화 내역 없음</p>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {messages.map((m) => (
        <div key={m.id || `${m.role}-${m.created_at}`} style={{ display: 'flex', flexDirection: 'column', alignItems: ROLE_ALIGN[m.role] || 'flex-start' }}>
          <span style={{ fontSize: 10, color: '#718096', marginBottom: 2 }}>{ROLE_LABEL[m.role] || m.role}</span>
          <div style={{
            background: ROLE_BG[m.role] || '#edf2f7',
            borderRadius: 8,
            padding: '6px 10px',
            maxWidth: '80%',
            fontSize: 13,
            lineHeight: 1.5,
          }}>
            {m.content}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

function EscalationCard({ esc, onUpdate, incomingMessage }: { esc: EscalationOut; onUpdate: () => void; incomingMessage: ChatMsg | null }) {
  const [msg, setMsg] = useState('')
  const [sending, setSending] = useState(false)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const typingDebounceRef = useRef<number | undefined>(undefined)

  useEffect(() => {
    getEscalationMessages(esc.id).then(data => {
      if (Array.isArray(data)) setMessages(data)
    })
  }, [esc.id])

  useEffect(() => {
    if (incomingMessage) {
      setMessages(prev => [...prev, incomingMessage])
    }
  }, [incomingMessage])

  const handleClaim = async () => {
    const res = await claimEscalation(esc.id)
    if (res.status === 200 || res.ok) onUpdate()
    else if (res.status === 409) alert('이미 다른 상담원이 수락한 세션입니다.')
  }

  const handleMsgChange = (e: ChangeEvent<HTMLInputElement>) => {
    setMsg(e.target.value)
    clearTimeout(typingDebounceRef.current)
    typingDebounceRef.current = window.setTimeout(() => {
      sendTypingIndicator(esc.id)
    }, 500)
  }

  const handleSend = async () => {
    if (!msg.trim()) return
    clearTimeout(typingDebounceRef.current)
    setSending(true)
    const content = msg.trim()
    setMsg('')
    await sendEscalationMessage(esc.id, content)
    setMessages(prev => [...prev, { role: 'human_agent', content, created_at: new Date().toISOString() }])
    setSending(false)
  }

  const handleResolve = async () => {
    await resolveEscalation(esc.id)
    onUpdate()
  }

  const isPending = esc.status === 'pending'
  const isClaimed = esc.status === 'claimed'

  return (
    <div style={{
      border: `2px solid ${isPending ? '#e53e3e' : '#e2e8f0'}`,
      borderRadius: 8,
      padding: 16,
      marginBottom: 12,
      background: isPending ? '#fff5f5' : '#fff',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontWeight: 600, fontSize: 13 }}>세션 {esc.session_id.slice(0, 8)}…</span>
        <span style={{ fontSize: 12, color: STATUS_COLOR[esc.status], fontWeight: 600 }}>
          {STATUS_LABEL[esc.status]}
        </span>
      </div>
      {esc.reason && <p style={{ fontSize: 12, color: '#718096', marginBottom: 8 }}>{esc.reason}</p>}

      <div style={{
        background: '#f7fafc',
        borderRadius: 6,
        padding: 10,
        maxHeight: 240,
        overflowY: 'auto',
        marginBottom: 10,
      }}>
        <ChatHistory messages={messages} />
      </div>

      {isPending && (
        <button style={{ ...s.btn, fontSize: 13, padding: '6px 14px' }} onClick={handleClaim}>
          수락하기
        </button>
      )}

      {isClaimed && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <input
              style={{ ...s.input, flex: 1 }}
              value={msg}
              onChange={handleMsgChange}
              placeholder="방문자에게 메시지 전송..."
              onKeyDown={e => e.key === 'Enter' && handleSend()}
              disabled={sending}
            />
            <button style={s.btn} onClick={handleSend} disabled={sending || !msg.trim()}>
              전송
            </button>
          </div>
          <button
            style={{ ...s.btnSm, background: '#fff', border: '1px solid #e2e8f0', color: '#718096' }}
            onClick={handleResolve}
          >
            AI에게 넘기기
          </button>
        </div>
      )}
    </div>
  )
}

export default function HitlTab() {
  const [escalations, setEscalations] = useState<EscalationOut[]>([])
  const [loading, setLoading] = useState(true)
  const [incomingBySession, setIncomingBySession] = useState<Record<string, ChatMsg>>({})
  const esRef = useRef<StreamHandle | null>(null)

  const refresh = () => {
    listEscalations().then(data => {
      setEscalations(data)
      setLoading(false)
    })
  }

  useEffect(() => {
    refresh()

    esRef.current = openEscalationStream((event) => {
      if (event.type === 'visitor_message') {
        const msg: ChatMsg = {
          role: 'user',
          content: event.content,
          created_at: new Date().toISOString(),
        }
        setIncomingBySession(prev => ({ ...prev, [event.session_id]: msg }))
      } else {
        refresh()
      }
    })

    return () => esRef.current?.close()
  }, [])

  if (loading) return <p>로딩 중...</p>

  return (
    <div style={{ maxWidth: 700 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>HITL 상담 세션</h3>
        <button style={s.btnSm} onClick={refresh}>새로고침</button>
      </div>

      {escalations.length === 0 ? (
        <p style={{ color: '#718096', fontSize: 14 }}>활성 세션이 없습니다.</p>
      ) : (
        escalations.map(esc => (
          <EscalationCard
            key={esc.id}
            esc={esc}
            onUpdate={refresh}
            incomingMessage={incomingBySession[esc.session_id] ?? null}
          />
        ))
      )}
    </div>
  )
}
