import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../api', () => ({
  tenantUsage: vi.fn().mockResolvedValue({
    total_tokens: 42,
    by_call_type: [
      { call_type: 'chat', input_tokens: 10, output_tokens: 5, total_tokens: 15, request_count: 1 },
      { call_type: 'embedding', input_tokens: 27, output_tokens: 0, total_tokens: 27, request_count: 3 },
    ],
    daily: [{ date: '2026-06-24', total_tokens: 42 }],
  }),
  operatorUsage: vi.fn().mockResolvedValue({
    total_tokens: 99,
    by_tenant: [{ tenant_id: 't1', tenant_name: 'Acme', total_tokens: 99, request_count: 4 }],
    daily: [{ date: '2026-06-24', total_tokens: 99 }],
  }),
}))

import TenantUsageTab from './TenantUsageTab'
import OperatorUsageTab from './OperatorUsageTab'

describe('TenantUsageTab', () => {
  it('총 토큰과 유형별 행을 렌더한다', async () => {
    render(<TenantUsageTab />)
    expect(await screen.findByTestId('usage-total')).toHaveTextContent('42')
    expect(screen.getByText('chat')).toBeInTheDocument()
    expect(screen.getByText('embedding')).toBeInTheDocument()
    expect(screen.getAllByTestId('usage-row')).toHaveLength(2)
  })
})

describe('OperatorUsageTab', () => {
  it('전체 총 토큰과 테넌트별 행을 렌더한다', async () => {
    render(<OperatorUsageTab />)
    expect(await screen.findByTestId('usage-total')).toHaveTextContent('99')
    expect(screen.getByText('Acme')).toBeInTheDocument()
    expect(screen.getAllByTestId('tenant-row')).toHaveLength(1)
  })
})
