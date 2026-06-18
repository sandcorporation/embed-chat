import { useState, useEffect, useRef, useCallback } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE || ''

export default function ChatWidget({ slug, visitorId }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState(null)
  const [status, setStatus] = useState('connecting') // connecting | ready | streaming | error
  const [streamingText, setStreamingText] = useState('')
  const [isHitl, setIsHitl] = useState(false)
  const [typingActor, setTypingActor] = useState(null) // null | 'ai' | 'human_agent'
  const typingTimerRef = useRef(null)
  const bottomRef = useRef(null)
  const eventSourceRef = useRef(null)

  useEffect(() => {
    const es = new EventSource(
      `${API_BASE}/api/chat/stream?slug=${encodeURIComponent(slug)}&visitor_id=${encodeURIComponent(visitorId)}`
    )
    eventSourceRef.current = es

    es.addEventListener('connected', (e) => {
      const data = JSON.parse(e.data)
      setSessionId(data.session_id)
      setStatus('ready')
      if (data.history) {
        setMessages(data.history)
        if (data.is_hitl) setIsHitl(true)
      } else if (data.welcome_message) {
        setMessages(msgs => [...msgs, { role: 'assistant', content: data.welcome_message }])
      }
    })

    es.addEventListener('token', (e) => {
      const data = JSON.parse(e.data)
      setTypingActor(null)
      setStreamingText(prev => prev + data.content)
    })

    es.addEventListener('done', () => {
      setTypingActor(null)
      setStreamingText(prev => {
        if (prev) {
          setMessages(msgs => [...msgs, { role: 'assistant', content: prev }])
        }
        return ''
      })
      setStatus('ready')
    })

    es.addEventListener('typing', (e) => {
      const data = JSON.parse(e.data)
      setTypingActor(data.actor)
      clearTimeout(typingTimerRef.current)
      typingTimerRef.current = setTimeout(() => setTypingActor(null), 3000)
    })

    es.addEventListener('hitl_start', () => {
      setIsHitl(true)
      setTypingActor(null)
      setStreamingText('')
      setStatus('ready')
      setMessages(msgs => [...msgs, {
        role: 'system',
        content: '잠시만 기다려 주세요. 상담원과 연결 중입니다.',
      }])
    })

    es.addEventListener('hitl_message', (e) => {
      const data = JSON.parse(e.data)
      setTypingActor(null)
      clearTimeout(typingTimerRef.current)
      setMessages(msgs => [...msgs, {
        role: 'human_agent',
        content: data.content,
        agentName: data.agent_display_name || '상담원',
      }])
    })

    es.addEventListener('hitl_end', () => {
      setIsHitl(false)
      setMessages(msgs => [...msgs, {
        role: 'system',
        content: 'AI 상담으로 전환되었습니다.',
      }])
    })

    es.addEventListener('error', () => setStatus('error'))

    es.onerror = () => {
      setStatus('error')
      es.close()
    }

    return () => {
      es.close()
      clearTimeout(typingTimerRef.current)
    }
  }, [slug, visitorId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText])

  const sendMessage = useCallback(async () => {
    if (!input.trim() || !sessionId || status === 'streaming') return

    const userMsg = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    if (!isHitl) setStatus('streaming')

    try {
      const res = await fetch(`${API_BASE}/api/chat/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, content: userMsg }),
      })
      if (res.ok && !isHitl) {
        setTypingActor('ai')
      }
    } catch {
      setStatus('error')
    }
  }, [input, sessionId, status, isHitl])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div style={styles.headerDot(status)} />
        <span>{isHitl ? '상담원 연결 중' : 'AI 상담'}</span>
      </div>

      <div style={styles.messages}>
        {messages.map((msg, i) => (
          <div key={i} style={styles.message(msg.role)}>
            {msg.role === 'human_agent' && (
              <div style={styles.agentName}>{msg.agentName}</div>
            )}
            <div data-role={msg.role} style={styles.bubble(msg.role)}>{msg.content}</div>
          </div>
        ))}
        {streamingText && (
          <div style={styles.message('assistant')}>
            <div style={styles.bubble('assistant')}>
              {streamingText}
              <span style={styles.cursor}>▌</span>
            </div>
          </div>
        )}
        {!streamingText && typingActor && (
          <div style={styles.message(typingActor === 'human_agent' ? 'human_agent' : 'assistant')}>
            <div style={{ ...styles.bubble(typingActor === 'human_agent' ? 'human_agent' : 'assistant'), opacity: 0.7 }}>
              <span style={styles.typingDots}>
                {typingActor === 'human_agent' ? '상담원이 입력 중' : 'AI가 응답 중'}
                <span style={styles.dots}>···</span>
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div style={styles.inputArea}>
        <textarea
          style={styles.textarea}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="메시지를 입력하세요..."
          disabled={status === 'connecting' || status === 'error'}
          rows={2}
        />
        <button
          style={styles.sendBtn(status !== 'connecting' && status !== 'error' && !!input.trim())}
          onClick={sendMessage}
          disabled={status === 'connecting' || status === 'error' || !input.trim()}
        >
          전송
        </button>
      </div>
    </div>
  )
}

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    background: '#fff',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '12px 16px',
    borderBottom: '1px solid #e2e8f0',
    fontWeight: 600,
    fontSize: '15px',
  },
  headerDot: (status) => ({
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    background: status === 'ready' ? '#48bb78' : status === 'error' ? '#fc8181' : '#ed8936',
  }),
  messages: {
    flex: 1,
    overflowY: 'auto',
    padding: '16px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  message: (role) => ({
    display: 'flex',
    flexDirection: 'column',
    alignItems: role === 'user' ? 'flex-end'
      : role === 'system' ? 'center'
        : 'flex-start',
  }),
  agentName: {
    fontSize: 11,
    color: '#718096',
    marginBottom: 2,
    paddingLeft: 4,
  },
  bubble: (role) => ({
    maxWidth: role === 'system' ? '90%' : '75%',
    padding: role === 'system' ? '6px 12px' : '10px 14px',
    borderRadius: role === 'user' ? '18px 18px 4px 18px'
      : role === 'system' ? '8px'
        : '18px 18px 18px 4px',
    background: role === 'user' ? '#4299e1'
      : role === 'human_agent' ? '#9f7aea'
        : role === 'system' ? '#ecc94b22'
          : '#edf2f7',
    color: role === 'user' ? '#fff'
      : role === 'human_agent' ? '#fff'
        : role === 'system' ? '#744210'
          : '#2d3748',
    fontSize: role === 'system' ? '12px' : '14px',
    lineHeight: '1.5',
    whiteSpace: 'pre-wrap',
    fontStyle: role === 'system' ? 'italic' : 'normal',
  }),
  cursor: {
    animation: 'blink 1s step-end infinite',
    opacity: 0.7,
  },
  typingDots: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    fontSize: 13,
  },
  dots: {
    animation: 'blink 1.2s step-end infinite',
    letterSpacing: 2,
  },
  inputArea: {
    display: 'flex',
    gap: '8px',
    padding: '12px 16px',
    borderTop: '1px solid #e2e8f0',
  },
  textarea: {
    flex: 1,
    resize: 'none',
    border: '1px solid #e2e8f0',
    borderRadius: '8px',
    padding: '8px 12px',
    fontSize: '14px',
    outline: 'none',
    fontFamily: 'inherit',
  },
  sendBtn: (enabled) => ({
    padding: '0 20px',
    borderRadius: '8px',
    border: 'none',
    background: enabled ? '#4299e1' : '#e2e8f0',
    color: enabled ? '#fff' : '#a0aec0',
    cursor: enabled ? 'pointer' : 'not-allowed',
    fontWeight: 600,
    fontSize: '14px',
    transition: 'all 0.2s',
  }),
}
