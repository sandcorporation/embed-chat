import { useState, useEffect, useRef } from 'react'
import { getSessionMessages, getSessionCheckpoint } from '../api'
import { s } from '../styles'

const ROLE_LABEL = { user: 'Visitor', assistant: 'AI', human_agent: '상담원' }
const ROLE_ALIGN = { user: 'flex-end', assistant: 'flex-start', human_agent: 'flex-start' }
const ROLE_BG = { user: '#4299e1', assistant: '#edf2f7', human_agent: '#9f7aea' }
const ROLE_COLOR = { user: '#fff', assistant: '#2d3748', human_agent: '#fff' }

function ChatHistory({ messages }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (!messages.length) {
    return <p style={{ fontSize: 12, color: '#a0aec0', textAlign: 'center', padding: '20px 0' }}>대화 내역 없음</p>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {messages.map((m, i) => (
        <div key={m.id || i} style={{ display: 'flex', flexDirection: 'column', alignItems: ROLE_ALIGN[m.role] || 'flex-start' }}>
          <span style={{ fontSize: 10, color: '#718096', marginBottom: 2 }}>
            {ROLE_LABEL[m.role] || m.role}
          </span>
          <div style={{
            background: ROLE_BG[m.role] || '#edf2f7',
            color: ROLE_COLOR[m.role] || '#2d3748',
            borderRadius: 8,
            padding: '8px 12px',
            maxWidth: '75%',
            fontSize: 13,
            lineHeight: 1.5,
            whiteSpace: 'pre-wrap',
          }}>
            {m.content}
          </div>
          {m.created_at && (
            <span style={{ fontSize: 10, color: '#a0aec0', marginTop: 2 }}>
              {new Date(m.created_at).toLocaleString()}
            </span>
          )}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

function CheckpointView({ agentToken, sessionId }) {
  const [data, setData] = useState(undefined)

  useEffect(() => {
    getSessionCheckpoint(agentToken, sessionId).then(setData)
  }, [sessionId, agentToken])

  if (data === undefined) return <p style={{ fontSize: 13, color: '#a0aec0' }}>불러오는 중...</p>
  if (data === null) return (
    <p style={{ fontSize: 13, color: '#718096' }}>이 세션은 AI 호출 내역이 없습니다.</p>
  )

  return (
    <pre style={{
      background: '#f7fafc',
      border: '1px solid #e2e8f0',
      borderRadius: 6,
      padding: 12,
      fontSize: 11,
      lineHeight: 1.6,
      overflowY: 'auto',
      maxHeight: 400,
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-all',
    }}>
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

export default function SessionDetail({ agentToken, sessionId, onBack }) {
  const [subTab, setSubTab] = useState('history')
  const [messages, setMessages] = useState([])

  useEffect(() => {
    getSessionMessages(agentToken, sessionId).then(data => {
      setMessages(Array.isArray(data) ? data : [])
    })
  }, [sessionId, agentToken])

  return (
    <div>
      <button style={{ ...s.btnSm, marginBottom: 16 }} onClick={onBack}>← 뒤로</button>

      <div style={{ fontSize: 12, color: '#718096', marginBottom: 12 }}>
        세션 <strong>{sessionId.slice(0, 8)}…</strong>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, borderBottom: '1px solid #e2e8f0', paddingBottom: 8 }}>
        {['history', 'checkpoint'].map(t => (
          <button
            key={t}
            style={{
              ...s.btnSm,
              background: subTab === t ? '#4299e1' : '#f7fafc',
              color: subTab === t ? '#fff' : '#4a5568',
              border: subTab === t ? 'none' : '1px solid #e2e8f0',
            }}
            onClick={() => setSubTab(t)}
          >
            {{ history: '대화 내역', checkpoint: 'Checkpoint' }[t]}
          </button>
        ))}
      </div>

      <div style={{ maxHeight: 480, overflowY: 'auto' }}>
        {subTab === 'history' && <ChatHistory messages={messages} />}
        {subTab === 'checkpoint' && (
          <CheckpointView agentToken={agentToken} sessionId={sessionId} />
        )}
      </div>
    </div>
  )
}
