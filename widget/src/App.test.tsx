import { describe, it, expect } from 'vitest'
import { resolveSlug } from './App'

// jsdom의 window.location.pathname을 테스트마다 교체한다(공개 URL 시뮬레이션).
function setPath(pathname: string) {
  Object.defineProperty(window, 'location', {
    value: { pathname, search: '' },
    writable: true,
    configurable: true,
  })
}

describe('resolveSlug (한글 공개 챗봇 URL — issue 187)', () => {
  it('percent-encoded 한글 path에서 NFC 슬러그를 추출한다', () => {
    setPath('/chatbot/' + encodeURIComponent('우리가게') + '/')
    expect(resolveSlug()).toBe('우리가게')
  })

  it('NFD(자모분리) 입력을 NFC로 정규화한다', () => {
    const nfd = '강남'.normalize('NFD')
    expect(nfd).not.toBe('강남'.normalize('NFC'))          // precondition
    setPath('/chatbot/' + encodeURIComponent(nfd) + '/')
    expect(resolveSlug()).toBe('강남'.normalize('NFC'))
  })

  it('평문 한글 path도 추출한다', () => {
    setPath('/chatbot/우리가게/')
    expect(resolveSlug()).toBe('우리가게')
  })

  it('기존 ASCII 슬러그를 유지한다(하위호환)', () => {
    setPath('/chatbot/abc-shop/')
    expect(resolveSlug()).toBe('abc-shop')
  })

  it('chatbot 경로가 아니면 빈 문자열', () => {
    setPath('/something/else/')
    expect(resolveSlug()).toBe('')
  })
})
