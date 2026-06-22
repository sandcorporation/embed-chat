import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import HitlTab from './HitlTab'
import * as api from '../api'

vi.mock('../api')

function esc(overrides = {}) {
  return { id: 'e1', session_id: 's-esc', trigger_type: 'ai', reason: '도움 요청', status: 'pending', created_at: '2026-06-22T00:00:00Z', ...overrides }
}
function sess(overrides = {}) {
  return { session_id: 's', visitor_id: 'v', is_hitl: false, escalation_status: '', active: false, created_at: '2026-06-22T00:00:00Z', last_activity: '2026-06-22T00:00:00Z', ...overrides }
}

function renderHitl() {
  return render(<MemoryRouter initialEntries={['/tenant/hitl']}><HitlTab /></MemoryRouter>)
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.openEscalationStream).mockReturnValue({ close: vi.fn() })
  vi.mocked(api.getEscalationMessages).mockResolvedValue([] as any)
})

describe('HitlTab — 세션 콘솔', () => {
  it('진행 중 상담은 카드(수락하기)로, 나머지 세션은 목록으로 보이고 escalation 세션은 목록에서 제외된다', async () => {
    vi.mocked(api.listEscalations).mockResolvedValue([esc()] as any)
    vi.mocked(api.listSessions).mockResolvedValue([
      sess({ session_id: 's-esc', visitor_id: 'visEsc', escalation_status: 'pending', is_hitl: true }),
      sess({ session_id: 's-idle', visitor_id: 'visIdle', last_activity: '2026-06-22T01:00:00Z' }),
      sess({ session_id: 's-active', visitor_id: 'visActive', active: true, last_activity: '2026-06-22T00:30:00Z' }),
    ] as any)

    renderHitl()

    // escalation은 카드로 — claim 버튼 노출(기존 동작 보존)
    expect(await screen.findByRole('button', { name: '수락하기' })).toBeInTheDocument()
    // 다른 세션 목록: escalation 세션(visEsc) 제외 → 2개
    const startBtns = screen.getAllByRole('button', { name: '상담 시작' })
    expect(startBtns).toHaveLength(2)
    expect(screen.queryByText('visEsc')).toBeNull()
    // 활성(visActive)이 유휴(visIdle)보다 위
    const labels = screen.getAllByText(/visActive|visIdle/)
    expect(labels[0]).toHaveTextContent('visActive')
  })

  it('"상담 시작"을 누르면 해당 세션을 takeover한다', async () => {
    vi.mocked(api.listEscalations).mockResolvedValue([] as any)
    vi.mocked(api.listSessions).mockResolvedValue([
      sess({ session_id: 's-idle', visitor_id: 'visIdle' }),
    ] as any)
    vi.mocked(api.takeoverSession).mockResolvedValue({ ok: true, status: 200, escalation_id: 'e-new' })

    renderHitl()
    await userEvent.click(await screen.findByRole('button', { name: '상담 시작' }))
    await waitFor(() => expect(api.takeoverSession).toHaveBeenCalledWith('s-idle'))
  })

  it('takeover가 409면 경고하고 새로고침하지 않는다', async () => {
    vi.mocked(api.listEscalations).mockResolvedValue([] as any)
    vi.mocked(api.listSessions).mockResolvedValue([sess({ session_id: 's-idle', visitor_id: 'visIdle' })] as any)
    vi.mocked(api.takeoverSession).mockResolvedValue({ ok: false, status: 409 })
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})

    renderHitl()
    await userEvent.click(await screen.findByRole('button', { name: '상담 시작' }))
    await waitFor(() => expect(alertSpy).toHaveBeenCalled())
    alertSpy.mockRestore()
  })
})
