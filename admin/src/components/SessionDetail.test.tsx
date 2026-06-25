import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as api from '../api'
import SessionDetail from './SessionDetail'

vi.mock('../api')

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.getSessionCheckpoint).mockResolvedValue(null as any)
  vi.mocked(api.getSessionRetrievals).mockResolvedValue([])
})

describe('SessionDetail — 대화 흐름 안의 검색 근거 (issue 207)', () => {
  it('대화 내역에서 유저 질문 다음에 그 턴의 검색 근거를 펼쳐본다(질문→검색→답변 순)', async () => {
    vi.mocked(api.getSessionMessages).mockResolvedValue([
      { id: 'u1', role: 'user', content: '해상도 알려줘', created_at: '2026-06-22T00:00:00Z' },
      { id: 'a1', role: 'assistant', content: '1920x1080입니다', created_at: '2026-06-22T00:00:01Z' },
    ] as any)
    vi.mocked(api.getSessionRetrievals).mockResolvedValue([
      { user_message: '해상도 알려줘', chunks: ['이 모니터는 1920 x 1080 FHD 해상도를 지원합니다.'], chunk_count: 1 },
    ])
    render(<SessionDetail sessionId="s1" onBack={() => {}} />)

    // 기본 '대화 내역' 탭에 질문·답변과 함께 검색 근거 토글이 인라인으로 있다(별도 탭 아님)
    expect(await screen.findByText('해상도 알려줘')).toBeInTheDocument()
    expect(screen.getByText('1920x1080입니다')).toBeInTheDocument()
    const toggle = screen.getByRole('button', { name: /검색된 근거 1개/ })

    await userEvent.click(toggle)
    expect(await screen.findByText(/1920 x 1080 FHD/)).toBeInTheDocument()
  })

  it('검색 근거 토글은 그 질문과 그 답변 사이에 놓인다(원인→결과 순서)', async () => {
    vi.mocked(api.getSessionMessages).mockResolvedValue([
      { id: 'u1', role: 'user', content: '질문A', created_at: '2026-06-22T00:00:00Z' },
      { id: 'a1', role: 'assistant', content: '답변A', created_at: '2026-06-22T00:00:01Z' },
    ] as any)
    vi.mocked(api.getSessionRetrievals).mockResolvedValue([
      { user_message: '질문A', chunks: ['근거A'], chunk_count: 1 },
    ])
    render(<SessionDetail sessionId="s2" onBack={() => {}} />)

    const q = await screen.findByText('질문A')
    const toggle = screen.getByRole('button', { name: /검색된 근거 1개/ })
    const a = screen.getByText('답변A')
    // DOM 순서: 질문 → 검색근거 토글 → 답변
    expect(q.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(toggle.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('검색 근거가 없는 세션은 토글 없이 대화만 보인다', async () => {
    vi.mocked(api.getSessionMessages).mockResolvedValue([
      { id: 'u1', role: 'user', content: '안녕', created_at: '2026-06-22T00:00:00Z' },
    ] as any)
    vi.mocked(api.getSessionRetrievals).mockResolvedValue([])
    render(<SessionDetail sessionId="s3" onBack={() => {}} />)

    expect(await screen.findByText('안녕')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /검색된 근거/ })).toBeNull()
  })
})
