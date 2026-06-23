import { describe, it, expect, vi } from 'vitest'
import { forwardRef } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import KGDemo from './KGDemo'

// canvas viz는 jsdom에서 못 그리므로 스텁(ref도 받게 forwardRef) — 데이터·리스트·확장만 검증.
vi.mock('react-force-graph-2d', () => ({ default: forwardRef(() => null) }))

describe('KGDemo (지식그래프 데모)', () => {
  it('목업 그래프의 노드 리스트를 렌더한다', () => {
    render(<KGDemo />)
    expect(screen.getByText('무선 이어폰')).toBeInTheDocument()
    expect(screen.getByText('노이즈 캔슬링')).toBeInTheDocument()
    expect(screen.getByText(/엔티티 5개/)).toBeInTheDocument()
  })

  it('노드를 클릭하면 이웃이 머지되어 그래프가 확장되고 디테일이 뜬다', () => {
    render(<KGDemo />)
    const before = screen.getAllByTestId('kg-node').length
    fireEvent.click(screen.getByText('배터리'))
    expect(screen.getByTestId('kg-detail')).toBeInTheDocument()
    expect(screen.getAllByTestId('kg-node').length).toBeGreaterThan(before)  // 충전 케이스 추가
  })
})
