import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createMockChatTransport } from './mockChatTransport'
import type { EventSourceLike } from '../transport'

describe('mockChatTransport', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('connected 후 질문에 맞는 답변을 토큰 델타로 흘리고 done한다', async () => {
    const t = createMockChatTransport({ stepMs: 10 })
    const events: { type: string; content?: string }[] = []
    const es: EventSourceLike = t.createEventSource('')
    es.addEventListener('connected', () => events.push({ type: 'connected' }))
    es.addEventListener('token', (e) => events.push({ type: 'token', content: JSON.parse(e.data).content }))
    es.addEventListener('done', () => events.push({ type: 'done' }))

    vi.advanceTimersByTime(1)            // setTimeout(0) connected
    expect(events[0].type).toBe('connected')

    await t.postMessage('demo', '지식그래프가 뭐죠?')
    vi.advanceTimersByTime(3000)         // 모든 토큰 + done

    const tokens = events.filter(e => e.type === 'token')
    expect(tokens.length).toBeGreaterThan(2)
    expect(tokens.map(e => e.content).join('')).toContain('지식그래프')
    expect(events[events.length - 1].type).toBe('done')
  })

  it('매칭 없는 질문은 기본 답변으로 폴백한다', async () => {
    const t = createMockChatTransport({ stepMs: 10 })
    const tokens: string[] = []
    const es: EventSourceLike = t.createEventSource('')
    es.addEventListener('token', (e) => tokens.push(JSON.parse(e.data).content))
    vi.advanceTimersByTime(1)

    await t.postMessage('demo', 'asdf 1234')
    vi.advanceTimersByTime(3000)

    expect(tokens.join('')).toContain('데모')
  })
})
