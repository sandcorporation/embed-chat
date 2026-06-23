import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import Markdown from './Markdown'
import { ChatHistory } from './SessionDetail'
import type { SessionMessageOut } from '../generated/model'

describe('admin Markdown', () => {
  it('굵게·리스트·링크를 서식으로 렌더하고 링크 보안 속성을 단다', () => {
    const { container } = render(<Markdown>{'**굵게**\n\n- a\n- b\n\n[문서](https://x.com)'}</Markdown>)
    expect(container.querySelector('strong')).toHaveTextContent('굵게')
    expect(container.querySelectorAll('li')).toHaveLength(2)
    const a = screen.getByRole('link', { name: '문서' })
    expect(a).toHaveAttribute('target', '_blank')
    expect(a).toHaveAttribute('rel', 'noopener noreferrer nofollow')
  })

  it('이미지는 미렌더, javascript: 링크는 차단한다', () => {
    const { container } = render(<Markdown>{'![a](https://x/y.png) [z](javascript:alert(1))'}</Markdown>)
    expect(container.querySelector('img')).toBeNull()
    const a = container.querySelector('a')
    expect(a?.getAttribute('href') || '').not.toMatch(/javascript:/i)
  })

  it('테이블을 가로 스크롤 컨테이너로 감싼다', () => {
    const { container } = render(<Markdown>{'| A | B |\n| - | - |\n| 1 | 2 |'}</Markdown>)
    const table = container.querySelector('table')
    expect(table).toBeInTheDocument()
    expect(table!.parentElement!.className).toContain('overflow-x-auto')
  })
})

describe('ChatHistory 마크다운 적용', () => {
  it('assistant 메시지는 마크다운으로, user 메시지는 평문으로 렌더한다', () => {
    const messages = [
      { id: '1', role: 'assistant', content: '**굵게** 답변' },
      { id: '2', role: 'user', content: '**평문** 질문' },
    ] as unknown as SessionMessageOut[]
    const { container } = render(<ChatHistory messages={messages} />)

    // assistant → strong 서식
    expect(container.querySelector('strong')).toHaveTextContent('굵게')
    // user → 리터럴 ** 유지(strong 1개뿐)
    expect(container.querySelectorAll('strong')).toHaveLength(1)
    expect(screen.getByText('**평문** 질문')).toBeInTheDocument()
  })
})
