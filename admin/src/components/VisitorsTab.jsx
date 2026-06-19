import { useState, useEffect } from 'react'
import { listVisitors, listVisitorSessions, listMemories, updateMemory, deleteMemory } from '../api'
import SessionDetail from './SessionDetail'
import { s } from '../styles'

const HITL_BADGE = {
  display: 'inline-block',
  fontSize: 10,
  fontWeight: 700,
  padding: '2px 6px',
  borderRadius: 4,
  background: '#9f7aea22',
  color: '#6b46c1',
  marginLeft: 6,
}

function VisitorList({ selectedId, onSelect }) {
  const [search, setSearch] = useState('')
  const [visitors, setVisitors] = useState([])

  const load = async (q) => {
    const data = await listVisitors(q || undefined)
    setVisitors(Array.isArray(data) ? data : [])
  }

  useEffect(() => { load('') }, [])

  return (
    <div style={{ width: 220, flexShrink: 0, borderRight: '1px solid #e2e8f0', paddingRight: 16 }}>
      <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
        <input
          style={{ ...s.input, flex: 1, fontSize: 12 }}
          placeholder="visitor_id 검색"
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && load(e.target.value)}
        />
        <button style={{ ...s.btnSm, flexShrink: 0 }} onClick={() => load(search)}>검색</button>
      </div>
      {visitors.length === 0 && (
        <p style={{ fontSize: 12, color: '#a0aec0' }}>방문자 없음</p>
      )}
      {visitors.map(v => (
        <div
          key={v.visitor_id}
          onClick={() => onSelect(v.visitor_id)}
          style={{
            padding: '8px 10px',
            borderRadius: 6,
            marginBottom: 4,
            cursor: 'pointer',
            fontSize: 13,
            background: selectedId === v.visitor_id ? '#ebf8ff' : 'transparent',
            border: selectedId === v.visitor_id ? '1px solid #bee3f8' : '1px solid transparent',
            wordBreak: 'break-all',
          }}
        >
          {v.visitor_id}
        </div>
      ))}
    </div>
  )
}

function SessionList({ visitorId, onSelectSession }) {
  const [sessions, setSessions] = useState([])

  useEffect(() => {
    listVisitorSessions(visitorId).then(data => {
      setSessions(Array.isArray(data) ? data : [])
    })
  }, [visitorId])

  if (sessions.length === 0) {
    return <p style={{ fontSize: 12, color: '#a0aec0' }}>세션 없음</p>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {sessions.map(sess => (
        <div
          key={sess.session_id}
          onClick={() => onSelectSession(sess.session_id)}
          style={{
            padding: '10px 12px',
            border: '1px solid #e2e8f0',
            borderRadius: 8,
            cursor: 'pointer',
            background: '#f7fafc',
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            {sess.session_id.slice(0, 8)}…
            {sess.is_hitl && <span style={HITL_BADGE}>HITL</span>}
          </div>
          <div style={{ fontSize: 11, color: '#718096', marginTop: 2 }}>
            {new Date(sess.created_at).toLocaleString()}
          </div>
        </div>
      ))}
    </div>
  )
}

function MemoryEditor({ visitorId }) {
  const [memories, setMemories] = useState([])
  const [editing, setEditing] = useState(null)

  useEffect(() => {
    listMemories(visitorId).then(data => {
      setMemories(Array.isArray(data) ? data : [])
    })
  }, [visitorId])

  const handleDelete = async (memId) => {
    await deleteMemory(visitorId, memId)
    setMemories(m => m.filter(x => x.id !== memId))
  }

  const handleUpdate = async (mem) => {
    const updated = await updateMemory(visitorId, mem.id, { key: mem.key, value: mem.value })
    setMemories(m => m.map(x => x.id === mem.id ? updated : x))
    setEditing(null)
  }

  if (memories.length === 0) {
    return <p style={{ fontSize: 12, color: '#a0aec0' }}>Memory 없음</p>
  }

  return (
    <table style={s.table}>
      <thead>
        <tr>
          <th style={s.th}>Key</th>
          <th style={s.th}>Value</th>
          <th style={s.th}>작업</th>
        </tr>
      </thead>
      <tbody>
        {memories.map(m => (
          <tr key={m.id}>
            <td style={s.td}>
              {editing?.id === m.id
                ? <input style={s.input} value={editing.key} onChange={e => setEditing(x => ({ ...x, key: e.target.value }))} />
                : m.key}
            </td>
            <td style={s.td}>
              {editing?.id === m.id
                ? <input style={s.input} value={editing.value} onChange={e => setEditing(x => ({ ...x, value: e.target.value }))} />
                : m.value}
            </td>
            <td style={s.td}>
              {editing?.id === m.id
                ? <>
                    <button style={s.btnSm} onClick={() => handleUpdate(editing)}>저장</button>
                    <button style={{ ...s.btnSm, marginLeft: 4 }} onClick={() => setEditing(null)}>취소</button>
                  </>
                : <>
                    <button style={s.btnSm} onClick={() => setEditing({ ...m })}>수정</button>
                    <button style={{ ...s.btnDanger, marginLeft: 4 }} onClick={() => handleDelete(m.id)}>삭제</button>
                  </>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function VisitorsTab() {
  const [selectedVisitor, setSelectedVisitor] = useState(null)
  const [selectedSession, setSelectedSession] = useState(null)

  const handleSelectVisitor = (visitorId) => {
    setSelectedVisitor(visitorId)
    setSelectedSession(null)
  }

  return (
    <div style={{ display: 'flex', gap: 24, minHeight: 500 }}>
      <VisitorList
       
        selectedId={selectedVisitor}
        onSelect={handleSelectVisitor}
      />

      <div style={{ flex: 1, minWidth: 0 }}>
        {!selectedVisitor ? (
          <p style={{ color: '#a0aec0', fontSize: 14, paddingTop: 40, textAlign: 'center' }}>
            왼쪽에서 방문자를 선택하세요
          </p>
        ) : selectedSession ? (
          <SessionDetail
           
            sessionId={selectedSession}
            onBack={() => setSelectedSession(null)}
          />
        ) : (
          <div>
            <h4 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>
              {selectedVisitor}
            </h4>
            <Section title="세션 목록">
              <SessionList
               
                visitorId={selectedVisitor}
                onSelectSession={setSelectedSession}
              />
            </Section>
            <Section title="Memory">
              <MemoryEditor visitorId={selectedVisitor} />
            </Section>
          </div>
        )}
      </div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h5 style={{ margin: '0 0 8px', fontSize: 13, fontWeight: 600, color: '#4a5568' }}>{title}</h5>
      {children}
    </div>
  )
}

