import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import ConfigTab from './ConfigTab'
import * as api from '../api'

vi.mock('../api')

const baseConfig = {
  model_id: 'm', system_prompt: 's', agent_display_name: 'a',
  webhook_url: '', webhook_type: '', welcome_message: '',
  brand_name: '', hitl_enabled: true, require_identity_verification: false,
  llm_provider_type: '', llm_base_url: '', llm_api_key: '', extraction_model: '',
  embed_provider_type: '', embed_base_url: '', embed_api_key: '', embed_model: '', embed_dim: 1024,
}

function mockConfig(overrides = {}) {
  vi.mocked(api.getTenantConfig).mockResolvedValue({ ...baseConfig, ...overrides } as any)
  vi.mocked(api.updateTenantConfig).mockResolvedValue({} as any)
}

async function save() {
  await userEvent.click(screen.getByRole('button', { name: '저장' }))
}

beforeEach(() => {
  vi.clearAllMocks()
  mockConfig()
})

describe('ConfigTab — HITL 토글', () => {
  it('hitl_enabled 토글을 끄고 저장하면 hitl_enabled=false를 보낸다', async () => {
    render(<ConfigTab />)
    const toggle = await screen.findByLabelText('HITL 사용')
    expect(toggle).toBeChecked() // 기본 켜짐

    await userEvent.click(toggle)
    await save()

    await waitFor(() => {
      expect(api.updateTenantConfig).toHaveBeenCalledWith(
        expect.objectContaining({ hitl_enabled: false }),
      )
    })
  })
})

describe('ConfigTab — 브랜드/신원검증', () => {
  it('brand_name 입력을 저장 payload에 담는다', async () => {
    render(<ConfigTab />)
    await userEvent.type(await screen.findByLabelText('브랜드 텍스트'), 'ABC샵')
    await save()
    await waitFor(() => expect(api.updateTenantConfig).toHaveBeenCalledWith(
        expect.objectContaining({ brand_name: 'ABC샵' }),
    ))
  })

  it('신원검증 토글을 켜고 저장하면 require_identity_verification=true', async () => {
    render(<ConfigTab />)
    const toggle = await screen.findByLabelText('visitor_id 신원검증 요구')
    expect(toggle).not.toBeChecked()
    await userEvent.click(toggle)
    await save()
    await waitFor(() => expect(api.updateTenantConfig).toHaveBeenCalledWith(
        expect.objectContaining({ require_identity_verification: true }),
    ))
  })
})

describe('ConfigTab — LLM Provider', () => {
  it('LLM provider 설정을 저장 payload에 담는다', async () => {
    render(<ConfigTab />)
    await userEvent.selectOptions(await screen.findByLabelText('LLM Provider 타입'), 'custom')
    await userEvent.type(screen.getByLabelText('LLM Base URL'), 'https://x/v1')
    await userEvent.type(screen.getByLabelText('LLM API Key'), 'sk-llm')
    await userEvent.type(screen.getByLabelText('추출 모델'), 'gpt-4o-mini')
    await save()
    await waitFor(() => expect(api.updateTenantConfig).toHaveBeenCalledWith(expect.objectContaining({
      llm_provider_type: 'custom', llm_base_url: 'https://x/v1',
      llm_api_key: 'sk-llm', extraction_model: 'gpt-4o-mini',
    })))
  })
})

describe('ConfigTab — Embedding Provider', () => {
  it('embedding provider 설정(차원 포함)을 저장 payload에 담는다', async () => {
    render(<ConfigTab />)
    await userEvent.selectOptions(await screen.findByLabelText('Embedding Provider 타입'), 'openai')
    await userEvent.type(screen.getByLabelText('Embedding Base URL'), 'https://api.openai.com/v1')
    await userEvent.type(screen.getByLabelText('Embedding API Key'), 'sk-emb')
    await userEvent.type(screen.getByLabelText('Embedding 모델'), 'text-embedding-3-small')
    const dim = screen.getByLabelText('Embedding 차원')
    await userEvent.clear(dim)
    await userEvent.type(dim, '1536')
    await save()
    await waitFor(() => expect(api.updateTenantConfig).toHaveBeenCalledWith(expect.objectContaining({
      embed_provider_type: 'openai', embed_base_url: 'https://api.openai.com/v1',
      embed_api_key: 'sk-emb', embed_model: 'text-embedding-3-small', embed_dim: 1536,
    })))
  })
})

describe('ConfigTab — Tenant Slug', () => {
  it('slug 입력 후 Slug 저장을 누르면 updateTenantSlug를 호출한다', async () => {
    vi.mocked(api.updateTenantSlug).mockResolvedValue({ slug: 'abc-shop' } as any)
    render(<ConfigTab />)
    await userEvent.type(await screen.findByLabelText('Tenant Slug'), 'abc-shop')
    await userEvent.click(screen.getByRole('button', { name: /Slug 저장/ }))
    await waitFor(() => expect(api.updateTenantSlug).toHaveBeenCalledWith('abc-shop'))
  })
})
