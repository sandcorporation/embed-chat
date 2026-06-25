import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as api from '../api'
import { HttpError } from '../mutator'
import TenantLogin from './TenantLogin'

vi.mock('../api')

beforeEach(() => { vi.clearAllMocks() })

async function fillSignup(opts: { org?: string; user?: string; pw?: string; confirm?: string }) {
  await userEvent.click(screen.getByText('새 조직 만들기'))
  await userEvent.type(screen.getByPlaceholderText('조직 이름'), opts.org ?? 'NewCo')
  await userEvent.type(screen.getByPlaceholderText('사용자명'), opts.user ?? 'owner')
  await userEvent.type(screen.getByPlaceholderText('비밀번호'), opts.pw ?? 'pw12345678')
  await userEvent.type(screen.getByPlaceholderText('비밀번호 확인'), opts.confirm ?? opts.pw ?? 'pw12345678')
  await userEvent.click(screen.getByRole('button', { name: '가입하고 시작' }))
}

describe('TenantLogin — 가입/로그인 + 비밀번호 확인·정책 (issue 209·211)', () => {
  it('가입 성공 시 tenantSignup 호출 + onLogin', async () => {
    vi.mocked(api.tenantSignup).mockResolvedValue({ access_token: 't' } as any)
    const onLogin = vi.fn()
    render(<TenantLogin onLogin={onLogin} />)

    await fillSignup({ pw: 'pw12345678' })

    expect(api.tenantSignup).toHaveBeenCalledWith('NewCo', 'owner', 'pw12345678')
    expect(onLogin).toHaveBeenCalledWith('owner')
    expect(api.tenantAgentLogin).not.toHaveBeenCalled()
  })

  it('비밀번호 확인이 일치하지 않으면 막고 tenantSignup을 호출하지 않는다', async () => {
    render(<TenantLogin onLogin={vi.fn()} />)
    await fillSignup({ pw: 'pw12345678', confirm: 'different' })

    expect(await screen.findByText('비밀번호가 일치하지 않습니다.')).toBeInTheDocument()
    expect(api.tenantSignup).not.toHaveBeenCalled()
  })

  it('비밀번호 정책 위반(400)이면 백엔드 메시지를 보여준다', async () => {
    vi.mocked(api.tenantSignup).mockRejectedValue(new HttpError(400, '/x', { detail: '비밀번호는 8자 이상이어야 합니다.' }))
    render(<TenantLogin onLogin={vi.fn()} />)
    await fillSignup({ pw: 'weak', confirm: 'weak' })

    expect(await screen.findByText('비밀번호는 8자 이상이어야 합니다.')).toBeInTheDocument()
  })

  it('중복 조직 이름(409)이면 안내 메시지를 보여준다', async () => {
    vi.mocked(api.tenantSignup).mockRejectedValue(new HttpError(409, '/x'))
    render(<TenantLogin onLogin={vi.fn()} />)
    await fillSignup({ org: 'Dup', pw: 'pw12345678' })

    expect(await screen.findByText('이미 사용 중인 조직 이름입니다.')).toBeInTheDocument()
  })
})
