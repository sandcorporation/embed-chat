import { useState } from 'react'
import DocumentsTab from '../components/DocumentsTab'
import KnowledgeGraphTab from '../components/KnowledgeGraphTab'
import VisitorsTab from '../components/VisitorsTab'
import ConfigTab from '../components/ConfigTab'
import AgentsTab from '../components/AgentsTab'
import HitlTab from '../components/HitlTab'
import { s } from '../styles'

export default function TenantDashboard({ username, onLogout, onLogoutAll }) {
  const [tab, setTab] = useState('documents')

  return (
    <div style={s.page}>
      <div style={s.header}>
        <h1 style={s.pageTitle}>Tenant 대시보드</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 13, color: '#718096' }}>{username}</span>
          <button style={s.btnSm} onClick={onLogout}>로그아웃</button>
          <button style={s.btnSm} onClick={onLogoutAll}>모든 기기에서 로그아웃</button>
        </div>
      </div>

      <div style={s.tabs}>
        {['documents', 'graph', 'visitors', 'config', 'agents', 'hitl'].map(t => (
          <button
            key={t}
            style={s.tab(tab === t)}
            onClick={() => setTab(t)}
          >
            {{ documents: '📄 문서', graph: '🕸️ 지식그래프', visitors: '👤 Visitors', config: '⚙️ 설정', agents: '👥 팀원', hitl: '🎧 HITL 상담' }[t]}
          </button>
        ))}
      </div>

      <div style={s.tabContent}>
        {tab === 'documents' && <DocumentsTab />}
        {tab === 'graph' && <KnowledgeGraphTab />}
        {tab === 'visitors' && <VisitorsTab />}
        {tab === 'config' && <ConfigTab />}
        {tab === 'agents' && <AgentsTab />}
        {tab === 'hitl' && <HitlTab />}
      </div>
    </div>
  )
}
