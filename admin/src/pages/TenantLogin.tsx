import { useState, FormEvent } from 'react'
import { tenantAgentLogin, tenantSignup } from '../api'
import { HttpError } from '../mutator'
import { s } from '../styles'

export default function TenantLogin({ onLogin }: { onLogin: (username: string) => void }) {
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [tenantName, setTenantName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')

  const isSignup = mode === 'signup'

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    if (!tenantName.trim() || !username.trim() || !password) {
      setError('모든 필드를 입력하세요.')
      return
    }
    if (isSignup && password !== confirm) {
      setError('비밀번호가 일치하지 않습니다.')
      return
    }
    try {
      if (isSignup) await tenantSignup(tenantName.trim(), username.trim(), password)
      else await tenantAgentLogin(tenantName.trim(), username.trim(), password)
      onLogin(username.trim())
    } catch (err) {
      if (isSignup && err instanceof HttpError && err.status === 409) setError('이미 사용 중인 조직 이름입니다.')
      else if (isSignup && err instanceof HttpError && err.body && typeof err.body === 'object' && 'detail' in err.body) setError(String((err.body as { detail: unknown }).detail))
      else if (isSignup) setError('가입에 실패했습니다. 입력을 확인하세요.')
      else setError('Tenant 이름, 사용자명 또는 비밀번호가 올바르지 않습니다.')
    }
  }

  const switchMode = (next: 'login' | 'signup') => (e: FormEvent) => {
    e.preventDefault()
    setMode(next)
    setError('')
  }

  return (
    <div style={s.center}>
      <div style={s.card}>
        <h2 style={s.title}>{isSignup ? '조직 만들기' : 'Tenant 로그인'}</h2>
        <form onSubmit={handleSubmit} style={s.form}>
          <input style={s.input} placeholder="조직 이름" value={tenantName} onChange={e => setTenantName(e.target.value)} />
          <input style={s.input} placeholder="사용자명" value={username} onChange={e => setUsername(e.target.value)} />
          <input style={s.input} type="password" placeholder="비밀번호" value={password} onChange={e => setPassword(e.target.value)} />
          {isSignup && (
            <>
              <input style={s.input} type="password" placeholder="비밀번호 확인" value={confirm} onChange={e => setConfirm(e.target.value)} />
              <p style={{ fontSize: 12, color: '#718096' }}>8자 이상(영문·숫자·특수문자 3종) 또는 10자 이상(2종 이상)</p>
            </>
          )}
          {error && <p style={s.error}>{error}</p>}
          <button style={s.btn} type="submit">{isSignup ? '가입하고 시작' : '로그인'}</button>
        </form>
        <p style={{ marginTop: 16, fontSize: 13, color: '#718096' }}>
          {isSignup
            ? <>이미 조직이 있나요? <a href="#" onClick={switchMode('login')}>로그인</a></>
            : <>조직이 없나요? <a href="#" onClick={switchMode('signup')}>새 조직 만들기</a></>}
          {' · Operator는 '}
          <a href="/admin-ui/operator">여기</a>
        </p>
      </div>
    </div>
  )
}
