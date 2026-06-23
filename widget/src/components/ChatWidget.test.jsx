import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import ChatWidget from './ChatWidget'

// 결정적 EventSource Fake — 테스트가 SSE 이벤트를 직접 emit한다.
class MockEventSource {
  constructor(url) {
    this.url = url
    this.listeners = {}
    MockEventSource.instances.push(this)
  }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn) }
  removeEventListener() {}
  close() {}
  emit(type, data) {
    (this.listeners[type] || []).forEach(fn => fn({ data: JSON.stringify(data) }))
  }
}

beforeEach(() => {
  MockEventSource.instances = []
  global.EventSource = MockEventSource
  global.fetch = vi.fn(() => Promise.resolve({ ok: true }))
})

function connectWith(history) {
  render(<ChatWidget slug="t" visitorId="v" />)
  const es = MockEventSource.instances[0]
  act(() => { es.emit('connected', { session_id: 's1', history }) })
  return es
}

describe('ChatWidget 마크다운 챗버블', () => {
  it('assistant 메시지는 마크다운으로, user 메시지는 평문으로 렌더한다', () => {
    const { container } = render(<ChatWidget slug="t" visitorId="v" />)
    const es = MockEventSource.instances[0]
    act(() => {
      es.emit('connected', {
        session_id: 's1',
        history: [
          { role: 'assistant', content: '**굵게** 답변' },
          { role: 'user', content: '**평문** 질문' },
        ],
      })
    })

    // assistant 버블 → strong 서식
    const assistantBubble = container.querySelector('[data-role="assistant"]')
    expect(assistantBubble.querySelector('strong')).toHaveTextContent('굵게')

    // user 버블 → 마크다운 미적용(리터럴 ** 유지, strong 없음)
    const userBubble = container.querySelector('[data-role="user"]')
    expect(userBubble.querySelector('strong')).toBeNull()
    expect(userBubble).toHaveTextContent('**평문** 질문')
  })

  it('스트리밍 토큰이 누적되며 라이브로 마크다운 렌더된다(닫히면 서식)', () => {
    render(<ChatWidget slug="t" visitorId="v" />)
    const es = MockEventSource.instances[0]
    act(() => { es.emit('connected', { session_id: 's1' }) })

    // 미완성: 닫는 ** 전 → strong 없음
    act(() => { es.emit('token', { content: '**굵게' }) })
    expect(document.querySelector('strong')).toBeNull()

    // 닫히면 → strong 서식으로 스냅
    act(() => { es.emit('token', { content: '** 입니다' }) })
    const strong = document.querySelector('strong')
    expect(strong).toHaveTextContent('굵게')
  })
})
