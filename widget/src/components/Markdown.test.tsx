import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import Markdown from './Markdown'

describe('Markdown (위젯 AI 버블 렌더러)', () => {
  it('굵게·리스트·인라인코드를 서식으로 렌더한다', () => {
    const { container } = render(<Markdown>{'**굵게** 그리고 `코드`\n\n- 항목1\n- 항목2'}</Markdown>)
    expect(container.querySelector('strong')).toHaveTextContent('굵게')
    expect(container.querySelectorAll('li')).toHaveLength(2)
    expect(container.querySelector('code')).toHaveTextContent('코드')
  })

  it('코드펜스를 pre/code 블록으로 렌더한다', () => {
    const { container } = render(<Markdown>{'```\nnpm install\n```'}</Markdown>)
    const pre = container.querySelector('pre')!
    expect(pre).toBeInTheDocument()
    expect(pre.querySelector('code')).toHaveTextContent('npm install')
  })

  it('링크를 새 탭·보안 rel로 연다', () => {
    render(<Markdown>{'[문서](https://example.com)'}</Markdown>)
    const a = screen.getByRole('link', { name: '문서' })
    expect(a).toHaveAttribute('href', 'https://example.com')
    expect(a).toHaveAttribute('target', '_blank')
    expect(a).toHaveAttribute('rel', 'noopener noreferrer nofollow')
  })

  it('javascript: 링크는 href를 비워 차단한다', () => {
    render(<Markdown>{'[악성](javascript:alert(1))'}</Markdown>)
    const a = screen.getByText('악성').closest('a')
    expect(a?.getAttribute('href') || '').not.toMatch(/javascript:/i)
  })

  it('이미지는 렌더하지 않는다', () => {
    const { container } = render(<Markdown>{'![alt](https://example.com/x.png)'}</Markdown>)
    expect(container.querySelector('img')).toBeNull()
  })

  it('테이블을 가로 스크롤 컨테이너로 감싼다', () => {
    const md = '| A | B |\n| - | - |\n| 1 | 2 |'
    const { container } = render(<Markdown>{md}</Markdown>)
    const table = container.querySelector('table')!
    expect(table).toBeInTheDocument()
    expect(table.parentElement!.style.overflowX).toBe('auto')
  })
})
