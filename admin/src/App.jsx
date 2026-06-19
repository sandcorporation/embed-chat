import { Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import OperatorLogin from './pages/OperatorLogin'
import OperatorDashboard from './pages/OperatorDashboard'
import TenantLogin from './pages/TenantLogin'
import TenantDashboard from './pages/TenantDashboard'
import { getAccess, bootSilentRefresh } from './auth'
import { operatorLogout, operatorLogoutAll, agentLogout, agentLogoutAll } from './api'

export default function App() {
  // Operator: access는 sessionStorage, refresh는 httpOnly 쿠키(ADR-0013).
  const [operatorAuthed, setOperatorAuthed] = useState(() => !!getAccess('operator'))
  const [operatorBooting, setOperatorBooting] = useState(true)

  // TenantAgent: operator와 동일하게 access=sessionStorage, refresh=httpOnly 쿠키.
  // username은 비민감 표시값이라 localStorage에 두어 새로고침 후에도 표시한다.
  const [agentAuthed, setAgentAuthed] = useState(() => !!getAccess('agent'))
  const [agentBooting, setAgentBooting] = useState(true)
  const [agentUsername, setAgentUsername] = useState(() => localStorage.getItem('agent_username'))

  useEffect(() => {
    // 새로고침으로 sessionStorage access가 사라져도 refresh 쿠키로 무중단 복구
    Promise.all([
      bootSilentRefresh('operator').then((ok) => setOperatorAuthed(ok)).finally(() => setOperatorBooting(false)),
      bootSilentRefresh('agent').then((ok) => setAgentAuthed(ok)).finally(() => setAgentBooting(false)),
    ])
  }, [])

  const handleOperatorLogin = () => setOperatorAuthed(true)
  const handleOperatorLogout = async () => {
    await operatorLogout()  // 이 기기 세션 서버 폐기 + access 제거
    setOperatorAuthed(false)
  }
  const handleOperatorLogoutAll = async () => {
    await operatorLogoutAll()
    setOperatorAuthed(false)
  }

  const handleTenantLogin = (username) => {
    localStorage.setItem('agent_username', username)
    setAgentUsername(username)
    setAgentAuthed(true)
  }

  const endAgentSession = () => {
    localStorage.removeItem('agent_username')
    setAgentAuthed(false)
    setAgentUsername(null)
  }
  const handleTenantLogout = async () => {
    await agentLogout()
    endAgentSession()
  }
  const handleTenantLogoutAll = async () => {
    await agentLogoutAll()
    endAgentSession()
  }

  return (
    <Routes>
      <Route path="/" element={<Navigate to="/operator" replace />} />
      <Route
        path="/operator"
        element={
          operatorBooting
            ? null
            : operatorAuthed
              ? <OperatorDashboard onLogout={handleOperatorLogout} onLogoutAll={handleOperatorLogoutAll} />
              : <OperatorLogin onLogin={handleOperatorLogin} />
        }
      />
      <Route
        path="/tenant"
        element={
          agentBooting
            ? null
            : agentAuthed
              ? <TenantDashboard username={agentUsername} onLogout={handleTenantLogout} onLogoutAll={handleTenantLogoutAll} />
              : <TenantLogin onLogin={handleTenantLogin} />
        }
      />
    </Routes>
  )
}
