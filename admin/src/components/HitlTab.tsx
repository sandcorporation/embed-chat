import { useState, useEffect, useRef, ChangeEvent } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { listEscalations, claimEscalation, sendEscalationMessage, resolveEscalation, openEscalationStream, sendTypingIndicator, getEscalationMessages } from '../api'
import type { StreamHandle } from '../api'
import type { EscalationOut } from '../generated/model'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const STATUS_LABEL: Record<string, string> = { pending: '대기 중', claimed: '진행 중', resolved: '완료' }
const STATUS_VARIANT: Record<string, 'destructive' | 'default' | 'success'> = { pending: 'destructive', claimed: 'default', resolved: 'success' }
const ROLE_LABEL: Record<string, string> = { user: 'Visitor', assistant: 'AI', human_agent: '상담원' }
const ROLE_BUBBLE: Record<string, string> = { user: 'self-start bg-muted', assistant: 'self-end bg-sky-100 dark:bg-sky-900/40', human_agent: 'self-end bg-emerald-100 dark:bg-emerald-900/40' }

type ChatMsg = { id?: string; role: string; content: string; created_at?: string }

function ChatHistory({ messages }: { messages: ChatMsg[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  if (!messages.length) return <p className="py-2 text-center text-xs text-muted-foreground">대화 내역 없음</p>

  return (
    <div className="flex flex-col gap-1.5">
      {messages.map(m => (
        <div key={m.id || `${m.role}-${m.created_at}`} className={cn('flex flex-col', m.role === 'user' ? 'items-start' : 'items-end')}>
          <span className="mb-0.5 text-[10px] text-muted-foreground">{ROLE_LABEL[m.role] || m.role}</span>
          <div className={cn('max-w-[80%] rounded-lg px-2.5 py-1.5 text-sm leading-relaxed', ROLE_BUBBLE[m.role] || 'self-start bg-muted')}>{m.content}</div>
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
    getEscalationMessages(esc.id).then(data => { if (Array.isArray(data)) setMessages(data) })
  }, [esc.id])

  useEffect(() => {
    if (incomingMessage) setMessages(prev => [...prev, incomingMessage])
  }, [incomingMessage])

  const handleClaim = async () => {
    const res = await claimEscalation(esc.id)
    if (res.status === 200 || res.ok) onUpdate()
    else if (res.status === 409) alert('이미 다른 상담원이 수락한 세션입니다.')
  }

  const handleMsgChange = (e: ChangeEvent<HTMLInputElement>) => {
    setMsg(e.target.value)
    clearTimeout(typingDebounceRef.current)
    typingDebounceRef.current = window.setTimeout(() => sendTypingIndicator(esc.id), 500)
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

  const handleResolve = async () => { await resolveEscalation(esc.id); onUpdate() }

  const isPending = esc.status === 'pending'
  const isClaimed = esc.status === 'claimed'

  return (
    <Card className={cn('mb-3', isPending && 'border-destructive/60 bg-destructive/5')}>
      <CardContent className="space-y-2 pt-5">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold">세션 {esc.session_id.slice(0, 8)}…</span>
          <Badge variant={STATUS_VARIANT[esc.status] || 'secondary'}>{STATUS_LABEL[esc.status]}</Badge>
        </div>
        {esc.reason && <p className="text-xs text-muted-foreground">{esc.reason}</p>}

        <div className="max-h-60 overflow-y-auto rounded-md bg-muted/40 p-2.5">
          <ChatHistory messages={messages} />
        </div>

        {isPending && <Button size="sm" onClick={handleClaim}>수락하기</Button>}

        {isClaimed && (
          <div className="space-y-2">
            <div className="flex gap-2">
              <Input className="flex-1" value={msg} onChange={handleMsgChange}
                placeholder="방문자에게 메시지 전송..." onKeyDown={e => e.key === 'Enter' && handleSend()} disabled={sending} />
              <Button onClick={handleSend} disabled={sending || !msg.trim()}>전송</Button>
            </div>
            <Button size="sm" variant="outline" onClick={handleResolve}>AI에게 넘기기</Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// /tenant/hitl(목록) · /tenant/hitl/:escalationId(특정 상담 딥링크). SSE·claim/resolve는 보존(ADR-0014).
export default function HitlTab() {
  const { escalationId } = useParams<{ escalationId?: string }>()
  const navigate = useNavigate()
  const [escalations, setEscalations] = useState<EscalationOut[]>([])
  const [loading, setLoading] = useState(true)
  const [incomingBySession, setIncomingBySession] = useState<Record<string, ChatMsg>>({})
  const esRef = useRef<StreamHandle | null>(null)

  const refresh = () => {
    listEscalations().then(data => { setEscalations(data); setLoading(false) })
  }

  useEffect(() => {
    refresh()
    esRef.current = openEscalationStream((event) => {
      if (event.type === 'visitor_message') {
        const msg: ChatMsg = { role: 'user', content: event.content, created_at: new Date().toISOString() }
        setIncomingBySession(prev => ({ ...prev, [event.session_id]: msg }))
      } else {
        refresh()
      }
    })
    return () => esRef.current?.close()
  }, [])

  if (loading) return <p className="text-sm text-muted-foreground">로딩 중...</p>

  const visible = escalationId ? escalations.filter(e => e.id === escalationId) : escalations

  return (
    <div className="max-w-3xl">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold">HITL 상담 세션</h3>
        <div className="flex gap-2">
          {escalationId && <Button size="sm" variant="ghost" onClick={() => navigate('/tenant/hitl')}>← 전체 보기</Button>}
          <Button size="sm" variant="outline" onClick={refresh}>새로고침</Button>
        </div>
      </div>

      {visible.length === 0 ? (
        <p className="text-sm text-muted-foreground">활성 세션이 없습니다.</p>
      ) : (
        visible.map(esc => (
          <div key={esc.id}>
            {!escalationId && (
              <div className="mb-1 flex justify-end">
                <Button size="sm" variant="ghost" onClick={() => navigate(`/tenant/hitl/${esc.id}`)}>🔗 단독 보기</Button>
              </div>
            )}
            <EscalationCard esc={esc} onUpdate={refresh} incomingMessage={incomingBySession[esc.session_id] ?? null} />
          </div>
        ))
      )}
    </div>
  )
}
