import { useState, FormEvent } from 'react'
import { tenantAgentLogin } from '../api'
import { s } from '../styles'

export default function TenantLogin({ onLogin }: { onLogin: (username: string) => void }) {
  const [tenantName, setTenantName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!tenantName.trim() || !username.trim() || !password) {
      setError('모든 필드를 입력하세요.')
      return
    }
    try {
      await tenantAgentLogin(tenantName.trim(), username.trim(), password) // access는 sessionStorage에 저장됨
      onLogin(username.trim())
    } catch {
      setError('Tenant 이름, 사용자명 또는 비밀번호가 올바르지 않습니다.')
    }
  }

  return (
    <div style={s.center}>
      <div style={s.card}>
        <h2 style={s.title}>Tenant 로그인</h2>
        <form onSubmit={handleSubmit} style={s.form}>
          <input
            style={s.input}
            placeholder="Tenant 이름"
            value={tenantName}
            onChange={e => setTenantName(e.target.value)}
          />
          <input
            style={s.input}
            placeholder="사용자명"
            value={username}
            onChange={e => setUsername(e.target.value)}
          />
          <input
            style={s.input}
            type="password"
            placeholder="비밀번호"
            value={password}
            onChange={e => setPassword(e.target.value)}
          />
          {error && <p style={s.error}>{error}</p>}
          <button style={s.btn} type="submit">로그인</button>
        </form>
        <p style={{ marginTop: 16, fontSize: 13, color: '#718096' }}>
          Operator로 로그인하려면 <a href="/admin-ui/operator">여기</a>
        </p>
      </div>
    </div>
  )
}
