import '@testing-library/jest-dom'

// jsdom은 scrollIntoView를 구현하지 않는다 — ChatWidget의 자동 스크롤 effect용 no-op 폴리필.
if (!window.HTMLElement.prototype.scrollIntoView) {
  window.HTMLElement.prototype.scrollIntoView = () => {}
}
