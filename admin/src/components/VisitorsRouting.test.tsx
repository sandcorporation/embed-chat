import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import * as api from '../api'
import VisitorsTab from './VisitorsTab'
import SessionDetailPage from './SessionDetailPage'

vi.mock('../api')

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.listVisitors).mockResolvedValue([] as any)
  vi.mocked(api.listVisitorSessions).mockResolvedValue([] as any)
  vi.mocked(api.listMemories).mockResolvedValue([] as any)
  vi.mocked(api.getSessionMessages).mockResolvedValue([] as any)
  vi.mocked(api.getSessionCheckpoint).mockResolvedValue(null as any)
  vi.mocked(api.getSessionRetrievals).mockResolvedValue([] as any)
})

function at(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/tenant/visitors/:visitorId" element={<VisitorsTab />} />
        <Route path="/tenant/sessions/:sessionId" element={<SessionDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('Visitors/Session 자원 라우트(ADR-0017)', () => {
  it('/tenant/visitors/:visitorId가 그 방문자 뷰를 렌더한다(딥링크)', async () => {
    at('/tenant/visitors/visitor-abc')
    expect(await screen.findByText('visitor-abc')).toBeInTheDocument()
  })

  it('/tenant/sessions/:sessionId가 그 세션 상세를 렌더한다(딥링크)', async () => {
    at('/tenant/sessions/sess-12345678')
    expect(await screen.findByText(/sess-123/)).toBeInTheDocument()
  })
})
