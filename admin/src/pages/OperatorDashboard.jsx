import { useState, useEffect } from 'react'
import { listTenants, createTenant, suspendTenant, deleteTenant } from '../api'
import { s } from '../styles'

export default function OperatorDashboard({ token, onLogout }) {
  const [tenants, setTenants] = useState([])
  const [newName, setNewName] = useState('')
  const [createdKey, setCreatedKey] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    const data = await listTenants(token)
    setTenants(data)
  }

  useEffect(() => { load() }, [])

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!newName.trim()) return
    setLoading(true)
    const data = await createTenant(token, newName.trim())
    setCreatedKey({ name: data.name, key: data.tenant_key, agentUsername: data.agent_username, agentPassword: data.agent_temp_password })
    setNewName('')
    await load()
    setLoading(false)
  }

  const handleSuspend = async (id) => {
    await suspendTenant(token, id)
    await load()
  }

  const handleDelete = async (id) => {
    if (!confirm('삭제하시겠습니까?')) return
    await deleteTenant(token, id)
    await load()
  }

  return (
    <div style={s.page}>
      <div style={s.header}>
        <h1 style={s.pageTitle}>Operator 대시보드</h1>
        <button style={s.btnSm} onClick={onLogout}>로그아웃</button>
      </div>

      {createdKey && (
        <div style={s.alert}>
          <strong>{createdKey.name}</strong> 생성 완료. (1회만 표시됩니다)
          <br />
          TENANT_KEY: <code style={s.code}>{createdKey.key}</code>
          <br />
          초기 상담원 계정 — 사용자명: <code style={s.code}>{createdKey.agentUsername}</code>{' '}
          임시 비밀번호: <code style={s.code}>{createdKey.agentPassword}</code>
          <button style={{ marginLeft: 12 }} onClick={() => setCreatedKey(null)}>✕</button>
        </div>
      )}

      <div style={s.section}>
        <h2 style={s.sectionTitle}>새 Tenant 추가</h2>
        <form onSubmit={handleCreate} style={{ display: 'flex', gap: 8 }}>
          <input
            style={{ ...s.input, flex: 1 }}
            placeholder="고객사 이름"
            value={newName}
            onChange={e => setNewName(e.target.value)}
          />
          <button style={s.btn} type="submit" disabled={loading}>추가</button>
        </form>
      </div>

      <div style={s.section}>
        <h2 style={s.sectionTitle}>Tenant 목록</h2>
        <table style={s.table}>
          <thead>
            <tr>
              <th style={s.th}>이름</th>
              <th style={s.th}>상태</th>
              <th style={s.th}>생성일</th>
              <th style={s.th}>작업</th>
            </tr>
          </thead>
          <tbody>
            {tenants.map(t => (
              <tr key={t.id}>
                <td style={s.td}>{t.name}</td>
                <td style={s.td}>
                  <span style={s.badge(t.is_active)}>{t.is_active ? '활성' : '정지'}</span>
                </td>
                <td style={s.td}>{t.created_at ? new Date(t.created_at).toLocaleDateString('ko') : '-'}</td>
                <td style={s.td}>
                  {t.is_active && (
                    <button style={s.btnDanger} onClick={() => handleSuspend(t.id)}>정지</button>
                  )}
                  <button style={{ ...s.btnDanger, marginLeft: 4 }} onClick={() => handleDelete(t.id)}>삭제</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
