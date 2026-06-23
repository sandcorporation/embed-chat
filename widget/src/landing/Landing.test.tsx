import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import Landing from './Landing'

// react-force-graph는 canvas라 jsdom에서 렌더 못 함 → KGDemo의 viz는 스텁(데이터/리스트만 검증).
vi.mock('react-force-graph-2d', () => ({ default: () => null }))

describe('Landing (공개 랜딩)', () => {
  it('핵심 기능 카드 4개를 렌더한다', () => {
    render(<Landing />)
    expect(screen.getByText('지식그래프 기반 RAG')).toBeInTheDocument()
    expect(screen.getByText('실시간 토큰 스트리밍')).toBeInTheDocument()
    expect(screen.getByText('HITL 상담 전환')).toBeInTheDocument()
    expect(screen.getByText('임베드 위젯')).toBeInTheDocument()
  })

  it('운영자 로그인 CTA가 /admin-ui/를 가리킨다', () => {
    render(<Landing />)
    expect(screen.getByRole('link', { name: '운영자 로그인' })).toHaveAttribute('href', '/admin-ui/')
  })

  it('Contact에 mailto·tel 링크가 있다', () => {
    render(<Landing />)
    expect(screen.getByRole('link', { name: 'gksdjf1690@gmail.com' }))
      .toHaveAttribute('href', 'mailto:gksdjf1690@gmail.com')
    expect(screen.getByRole('link', { name: '010-2483-1690' }))
      .toHaveAttribute('href', 'tel:01024831690')
  })
})
