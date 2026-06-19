import { Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import OperatorLogin from './pages/OperatorLogin'
import OperatorDashboard from './pages/OperatorDashboard'
import TenantLogin from './pages/TenantLogin'
import TenantDashboard from './pages/TenantDashboard'
import { getAccess, clearAccess, bootSilentRefresh } from './auth'

export default function App() {
  // Operator: access는 sessionStorage, refresh는 httpOnly 쿠키(ADR-0013).
  const [operatorAuthed, setOperatorAuthed] = useState(() => !!getAccess('operator'))
  const [operatorBooting, setOperatorBooting] = useState(true)

  const [agentToken, setAgentToken] = useState(() => localStorage.getItem('agent_token'))
  const [agentUsername, setAgentUsername] = useState(() => localStorage.getItem('agent_username'))

  useEffect(() => {
    // 새로고침으로 sessionStorage access가 사라져도 refresh 쿠키로 무중단 복구
    bootSilentRefresh('operator')
      .then((ok) => setOperatorAuthed(ok))
      .finally(() => setOperatorBooting(false))
  }, [])

  const handleOperatorLogin = () => setOperatorAuthed(true)
  const handleOperatorLogout = () => {
    clearAccess('operator')
    setOperatorAuthed(false)
  }

  const handleTenantLogin = (token, username) => {
    localStorage.setItem('agent_token', token)
    localStorage.setItem('agent_username', username)
    setAgentToken(token)
    setAgentUsername(username)
  }

  const handleTenantLogout = () => {
    localStorage.removeItem('agent_token')
    localStorage.removeItem('agent_username')
    setAgentToken(null)
    setAgentUsername(null)
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
              ? <OperatorDashboard onLogout={handleOperatorLogout} />
              : <OperatorLogin onLogin={handleOperatorLogin} />
        }
      />
      <Route
        path="/tenant"
        element={
          agentToken
            ? <TenantDashboard agentToken={agentToken} username={agentUsername} onLogout={handleTenantLogout} />
            : <TenantLogin onLogin={handleTenantLogin} />
        }
      />
    </Routes>
  )
}
