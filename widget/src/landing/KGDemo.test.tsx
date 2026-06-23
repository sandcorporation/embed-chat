import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import KGDemo from './KGDemo'

// canvas viz는 jsdom에서 못 그리므로 스텁 — 데이터 매핑·리스트·확장 상호작용만 검증.
vi.mock('react-force-graph-2d', () => ({ default: () => null }))

describe('KGDemo (지식그래프 데모)', () => {
  it('목업 그래프의 노드 리스트를 렌더한다', () => {
    render(<KGDemo />)
    expect(screen.getByText(/FCB1010 매뉴얼/)).toBeInTheDocument()
    expect(screen.getByText(/풋스위치/)).toBeInTheDocument()
    expect(screen.getByText(/엔티티 4개/)).toBeInTheDocument()
  })

  it('노드를 클릭하면 이웃이 머지되어 그래프가 확장되고 디테일이 뜬다', () => {
    render(<KGDemo />)
    const before = screen.getAllByTestId('kg-node').length
    fireEvent.click(screen.getByText(/풋스위치/))
    expect(screen.getByTestId('kg-detail')).toBeInTheDocument()
    expect(screen.getAllByTestId('kg-node').length).toBeGreaterThan(before)  // 이웃 추가
  })
})
