import { useState, useEffect, useRef } from 'react'
import { getSessionMessages, getSessionCheckpoint } from '../api'
import type { SessionMessageOut } from '../generated/model'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import Markdown from './Markdown'

const ROLE_LABEL: Record<string, string> = { user: 'Visitor', assistant: 'AI', human_agent: '상담원' }
const ROLE_BUBBLE: Record<string, string> = {
  user: 'self-end bg-primary text-primary-foreground',
  assistant: 'self-start bg-muted text-foreground',
  human_agent: 'self-start bg-violet-500 text-white',
}

export function ChatHistory({ messages }: { messages: SessionMessageOut[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  if (!messages.length) return <p className="py-5 text-center text-xs text-muted-foreground">대화 내역 없음</p>

  return (
    <div className="flex flex-col gap-2">
      {messages.map((m, i) => (
        <div key={m.id || i} className={cn('flex flex-col', m.role === 'user' ? 'items-end' : 'items-start')}>
          <span className="mb-0.5 text-[10px] text-muted-foreground">{ROLE_LABEL[m.role] || m.role}</span>
          <div className={cn('max-w-[75%] rounded-lg px-3 py-2 text-sm leading-relaxed', m.role === 'assistant' ? '' : 'whitespace-pre-wrap', ROLE_BUBBLE[m.role] || 'self-start bg-muted')}>
            {m.role === 'assistant' ? <Markdown>{m.content}</Markdown> : m.content}
          </div>
          {m.created_at && <span className="mt-0.5 text-[10px] text-muted-foreground">{new Date(m.created_at).toLocaleString()}</span>}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

function CheckpointView({ sessionId }: { sessionId: string }) {
  const [data, setData] = useState<unknown>(undefined)
  useEffect(() => { getSessionCheckpoint(sessionId).then(setData) }, [sessionId])

  if (data === undefined) return <p className="text-sm text-muted-foreground">불러오는 중...</p>
  if (data === null) return <p className="text-sm text-muted-foreground">이 세션은 AI 호출 내역이 없습니다.</p>

  return (
    <pre className="max-h-[400px] overflow-y-auto whitespace-pre-wrap break-all rounded-md border border-border bg-muted/40 p-3 text-[11px] leading-relaxed">
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

export default function SessionDetail({ sessionId, onBack }: { sessionId: string; onBack: () => void }) {
  const [subTab, setSubTab] = useState('history')
  const [messages, setMessages] = useState<SessionMessageOut[]>([])

  useEffect(() => {
    getSessionMessages(sessionId).then(data => setMessages(Array.isArray(data) ? data : []))
  }, [sessionId])

  return (
    <div>
      <Button size="sm" variant="outline" className="mb-4" onClick={onBack}>← 뒤로</Button>
      <div className="mb-3 text-xs text-muted-foreground">세션 <strong>{sessionId.slice(0, 8)}…</strong></div>

      <div className="mb-4 flex gap-2 border-b border-border pb-2">
        {(['history', 'checkpoint'] as const).map(t => (
          <Button key={t} size="sm" variant={subTab === t ? 'default' : 'outline'} onClick={() => setSubTab(t)}>
            {{ history: '대화 내역', checkpoint: 'Checkpoint' }[t]}
          </Button>
        ))}
      </div>

      <div className="max-h-[480px] overflow-y-auto">
        {subTab === 'history' && <ChatHistory messages={messages} />}
        {subTab === 'checkpoint' && <CheckpointView sessionId={sessionId} />}
      </div>
    </div>
  )
}
