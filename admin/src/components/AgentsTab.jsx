import { useState, useEffect } from 'react'
import { listAgents, createAgent, deactivateAgent, changePassword } from '../api'
import { s } from '../styles'

export default function AgentsTab({ agentToken }) {
  const [agents, setAgents] = useState([])
  const [newUsername, setNewUsername] = useState('')
  const [createdCred, setCreatedCred] = useState(null)
  const [loading, setLoading] = useState(false)
  const [pwForm, setPwForm] = useState({ current: '', next: '', error: '', success: false })

  const load = async () => {
    const data = await listAgents(agentToken)
    setAgents(data)
  }

  useEffect(() => { load() }, [])

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!newUsername.trim()) return
    setLoading(true)
    const data = await createAgent(agentToken, newUsername.trim())
    setCreatedCred({ username: data.username, password: data.temp_password })
    setNewUsername('')
    await load()
    setLoading(false)
  }

  const handleDeactivate = async (id) => {
    if (!confirm('비활성화하시겠습니까?')) return
    await deactivateAgent(agentToken, id)
    await load()
  }

  const handleChangePassword = async (e) => {
    e.preventDefault()
    try {
      await changePassword(agentToken, pwForm.current, pwForm.next)
      setPwForm({ current: '', next: '', error: '', success: true })
      setTimeout(() => setPwForm(f => ({ ...f, success: false })), 2000)
    } catch (err) {
      setPwForm(f => ({ ...f, error: err.message }))
    }
  }

  return (
    <div>
      {createdCred && (
        <div style={s.alert}>
          <strong>{createdCred.username}</strong> 계정이 생성되었습니다.
          임시 비밀번호 (1회만 표시): <code style={s.code}>{createdCred.password}</code>
          <button style={{ marginLeft: 12 }} onClick={() => setCreatedCred(null)}>✕</button>
        </div>
      )}

      <div style={s.section}>
        <h2 style={s.sectionTitle}>팀원 추가</h2>
        <form onSubmit={handleCreate} style={{ display: 'flex', gap: 8 }}>
          <input
            style={{ ...s.input, flex: 1 }}
            placeholder="사용자명"
            value={newUsername}
            onChange={e => setNewUsername(e.target.value)}
          />
          <button style={s.btn} type="submit" disabled={loading}>추가</button>
        </form>
      </div>

      <div style={s.section}>
        <h2 style={s.sectionTitle}>팀원 목록</h2>
        <table style={s.table}>
          <thead>
            <tr>
              <th style={s.th}>사용자명</th>
              <th style={s.th}>상태</th>
              <th style={s.th}>작업</th>
            </tr>
          </thead>
          <tbody>
            {agents.map(a => (
              <tr key={a.id}>
                <td style={s.td}>{a.username}</td>
                <td style={s.td}>
                  <span style={s.badge(a.is_active)}>{a.is_active ? '활성' : '비활성'}</span>
                </td>
                <td style={s.td}>
                  {a.is_active && (
                    <button style={s.btnDanger} onClick={() => handleDeactivate(a.id)}>비활성화</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={s.section}>
        <h2 style={s.sectionTitle}>내 비밀번호 변경</h2>
        <form onSubmit={handleChangePassword} style={s.form}>
          <input
            style={s.input}
            type="password"
            placeholder="현재 비밀번호"
            value={pwForm.current}
            onChange={e => setPwForm(f => ({ ...f, current: e.target.value }))}
          />
          <input
            style={s.input}
            type="password"
            placeholder="새 비밀번호"
            value={pwForm.next}
            onChange={e => setPwForm(f => ({ ...f, next: e.target.value }))}
          />
          {pwForm.error && <p style={s.error}>{pwForm.error}</p>}
          <button style={s.btn} type="submit">
            {pwForm.success ? '✓ 변경됨' : '변경'}
          </button>
        </form>
      </div>
    </div>
  )
}
