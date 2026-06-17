import { Routes, Route, Navigate } from 'react-router-dom'
import { useState } from 'react'
import OperatorLogin from './pages/OperatorLogin'
import OperatorDashboard from './pages/OperatorDashboard'
import TenantLogin from './pages/TenantLogin'
import TenantDashboard from './pages/TenantDashboard'

export default function App() {
  const [operatorToken, setOperatorToken] = useState(() => localStorage.getItem('op_token'))
  const [agentToken, setAgentToken] = useState(() => localStorage.getItem('agent_token'))
  const [agentUsername, setAgentUsername] = useState(() => localStorage.getItem('agent_username'))

  const handleOperatorLogin = (token) => {
    localStorage.setItem('op_token', token)
    setOperatorToken(token)
  }

  const handleTenantLogin = (token, username) => {
    localStorage.setItem('agent_token', token)
    localStorage.setItem('agent_username', username)
    setAgentToken(token)
    setAgentUsername(username)
  }

  const handleOperatorLogout = () => {
    localStorage.removeItem('op_token')
    setOperatorToken(null)
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
          operatorToken
            ? <OperatorDashboard token={operatorToken} onLogout={handleOperatorLogout} />
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
