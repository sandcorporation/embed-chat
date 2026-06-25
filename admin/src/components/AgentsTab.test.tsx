import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as api from '../api'
import { HttpError } from '../mutator'
import AgentsTab from './AgentsTab'

vi.mock('../api')

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.listAgents).mockResolvedValue([
    { id: 'a1', username: 'owner', is_active: true, role: 'admin' },
    { id: 'a2', username: 'bob', is_active: true, role: 'member' },
  ] as any)
})

describe('AgentsTab — 역할 관리/게이팅 (issue 210)', () => {
  it('Admin은 역할을 보고 멤버를 승격할 수 있다', async () => {
    vi.mocked(api.currentAgentRole).mockReturnValue('admin')
    vi.mocked(api.changeAgentRole).mockResolvedValue({} as any)
    render(<AgentsTab />)

    expect(await screen.findByText('bob')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Admin으로' }))  // bob(member) 행
    expect(api.changeAgentRole).toHaveBeenCalledWith('a2', 'admin')
  })

  it('마지막 Admin 강등(409)이면 안내를 보여준다', async () => {
    vi.mocked(api.currentAgentRole).mockReturnValue('admin')
    vi.mocked(api.changeAgentRole).mockRejectedValue(new HttpError(409, '/x'))
    render(<AgentsTab />)

    await screen.findByText('owner')
    await userEvent.click(screen.getByRole('button', { name: 'Member로' }))  // owner(admin) 행
    expect(await screen.findByText('마지막 Admin은 강등할 수 없습니다.')).toBeInTheDocument()
  })

  it('Member는 팀원 관리 컨트롤을 보지 못한다(목록은 보임)', async () => {
    vi.mocked(api.currentAgentRole).mockReturnValue('member')
    render(<AgentsTab />)

    expect(await screen.findByText('owner')).toBeInTheDocument()
    expect(screen.getByText('팀원 관리는 Admin만 할 수 있습니다.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '추가' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Admin으로' })).toBeNull()
  })
})
