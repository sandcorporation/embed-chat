import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as api from '../api'
import SessionDetail from './SessionDetail'

vi.mock('../api')

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.getSessionMessages).mockResolvedValue([] as any)
  vi.mocked(api.getSessionCheckpoint).mockResolvedValue(null as any)
})

describe('SessionDetail 검색(retrievals) 탭 (issue 207)', () => {
  it('검색 탭에서 턴별 검색된 청크를 테넌트에게 보여준다', async () => {
    vi.mocked(api.getSessionRetrievals).mockResolvedValue([
      { user_message: '지원하는 모니터의 해상도', chunks: ['이 모니터는 1920 x 1080 FHD 해상도를 지원합니다.'], chunk_count: 1 },
    ])
    render(<SessionDetail sessionId="sess-123" onBack={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: '검색' }))

    expect(await screen.findByText(/1920 x 1080 FHD/)).toBeInTheDocument()
    expect(screen.getByText(/지원하는 모니터의 해상도/)).toBeInTheDocument()
    expect(screen.getByText(/검색된 청크 1개/)).toBeInTheDocument()
  })

  it('검색 내역이 없으면 안내 문구를 보여준다', async () => {
    vi.mocked(api.getSessionRetrievals).mockResolvedValue([])
    render(<SessionDetail sessionId="sess-456" onBack={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: '검색' }))

    expect(await screen.findByText('검색 내역이 없습니다.')).toBeInTheDocument()
  })
})
