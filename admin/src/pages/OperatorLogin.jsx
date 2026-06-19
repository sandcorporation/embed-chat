import { useState } from 'react'
import { operatorLogin } from '../api'
import { s } from '../styles'

export default function OperatorLogin({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    try {
      await operatorLogin(username, password) // access는 sessionStorage에 저장됨
      onLogin()
    } catch {
      setError('아이디 또는 비밀번호가 올바르지 않습니다.')
    }
  }

  return (
    <div style={s.center}>
      <div style={s.card}>
        <h2 style={s.title}>Operator 로그인</h2>
        <form onSubmit={handleSubmit} style={s.form}>
          <input style={s.input} placeholder="아이디" value={username} onChange={e => setUsername(e.target.value)} />
          <input style={s.input} type="password" placeholder="비밀번호" value={password} onChange={e => setPassword(e.target.value)} />
          {error && <p style={s.error}>{error}</p>}
          <button style={s.btn} type="submit">로그인</button>
        </form>
        <p style={{ marginTop: 16, fontSize: 13, color: '#718096' }}>
          Tenant로 로그인하려면 <a href="/admin-ui/tenant">여기</a>
        </p>
      </div>
    </div>
  )
}
