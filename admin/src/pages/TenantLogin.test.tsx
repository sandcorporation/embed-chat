import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as api from '../api'
import { HttpError } from '../mutator'
import TenantLogin from './TenantLogin'

vi.mock('../api')

beforeEach(() => { vi.clearAllMocks() })

describe('TenantLogin — 가입/로그인 토글 (issue 209)', () => {
  it('새 조직 만들기로 전환해 가입하면 tenantSignup 호출 + onLogin', async () => {
    vi.mocked(api.tenantSignup).mockResolvedValue({ access_token: 't' } as any)
    const onLogin = vi.fn()
    render(<TenantLogin onLogin={onLogin} />)

    await userEvent.click(screen.getByText('새 조직 만들기'))
    await userEvent.type(screen.getByPlaceholderText('조직 이름'), 'NewCo')
    await userEvent.type(screen.getByPlaceholderText('사용자명'), 'owner')
    await userEvent.type(screen.getByPlaceholderText('비밀번호'), 'pw12345678')
    await userEvent.click(screen.getByRole('button', { name: '가입하고 시작' }))

    expect(api.tenantSignup).toHaveBeenCalledWith('NewCo', 'owner', 'pw12345678')
    expect(onLogin).toHaveBeenCalledWith('owner')
    expect(api.tenantAgentLogin).not.toHaveBeenCalled()
  })

  it('중복 조직 이름(409)이면 안내 메시지를 보여준다', async () => {
    vi.mocked(api.tenantSignup).mockRejectedValue(new HttpError(409, '/api/tenant/agents/auth/signup'))
    render(<TenantLogin onLogin={vi.fn()} />)

    await userEvent.click(screen.getByText('새 조직 만들기'))
    await userEvent.type(screen.getByPlaceholderText('조직 이름'), 'Dup')
    await userEvent.type(screen.getByPlaceholderText('사용자명'), 'a')
    await userEvent.type(screen.getByPlaceholderText('비밀번호'), 'pw12345678')
    await userEvent.click(screen.getByRole('button', { name: '가입하고 시작' }))

    expect(await screen.findByText('이미 사용 중인 조직 이름입니다.')).toBeInTheDocument()
  })
})
