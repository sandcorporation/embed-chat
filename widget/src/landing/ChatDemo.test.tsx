import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ChatDemo from './ChatDemo'

describe('ChatDemo (Hero 챗봇 데모)', () => {
  it('실제 ChatWidget(입력창)과 추천 칩을 렌더한다', () => {
    render(<ChatDemo />)
    expect(screen.getByPlaceholderText('메시지를 입력하세요...')).toBeInTheDocument()
    expect(screen.getByText('지식그래프가 뭐죠?')).toBeInTheDocument()
    expect(screen.getByText('어떻게 삽입하나요?')).toBeInTheDocument()
  })
})
