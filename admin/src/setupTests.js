import '@testing-library/jest-dom'

// jsdom은 scrollIntoView를 구현하지 않는다 — 채팅 히스토리의 자동 스크롤 effect용 no-op 폴리필.
if (!window.HTMLElement.prototype.scrollIntoView) {
  window.HTMLElement.prototype.scrollIntoView = () => {}
}

// recharts ResponsiveContainer가 쓰는 ResizeObserver가 jsdom엔 없다 — no-op 폴리필.
if (!('ResizeObserver' in globalThis)) {
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
}
