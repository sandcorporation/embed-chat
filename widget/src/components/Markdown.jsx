import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// 링크 프로토콜 화이트리스트 — http/https/mailto + 스킴 없는 상대/앵커만 허용.
// javascript:·data: 등 다른 스킴은 href를 비워 실행/로드를 차단한다.
const SAFE_PROTOCOL = /^(https?:|mailto:):?/i

function safeUrl(url) {
  if (!url) return ''
  const u = String(url).trim()
  if (SAFE_PROTOCOL.test(u)) return u
  if (/^[a-z][a-z0-9+.-]*:/i.test(u)) return ''   // 다른 스킴(javascript:,data:…) → 제거
  return u                                          // 스킴 없음(상대/#앵커) → 허용
}

const S = {
  a: { color: '#3182ce', textDecoration: 'underline', wordBreak: 'break-word' },
  p: { margin: '0 0 8px' },
  ul: { margin: '4px 0', paddingLeft: 18 },
  ol: { margin: '4px 0', paddingLeft: 18 },
  li: { margin: '2px 0' },
  h: (em) => ({ margin: '8px 0 4px', fontWeight: 600, fontSize: em, lineHeight: 1.3 }),
  codeInline: { background: '#00000014', padding: '1px 5px', borderRadius: 4, fontFamily: 'monospace', fontSize: '0.9em' },
  codeBlock: { fontFamily: 'monospace', fontSize: '0.85em', whiteSpace: 'pre' },
  pre: { background: '#00000010', padding: 10, borderRadius: 6, overflowX: 'auto', margin: '6px 0' },
  bq: { borderLeft: '3px solid #cbd5e0', paddingLeft: 8, margin: '6px 0', color: '#4a5568' },
  tableWrap: { overflowX: 'auto', margin: '6px 0' },
  table: { borderCollapse: 'collapse', fontSize: '0.9em' },
  th: { border: '1px solid #cbd5e0', padding: '4px 8px', background: '#0000000a', textAlign: 'left' },
  td: { border: '1px solid #cbd5e0', padding: '4px 8px' },
  hr: { border: 0, borderTop: '1px solid #e2e8f0', margin: '8px 0' },
}

const components = {
  a: ({ href, children }) => (
    <a href={href || undefined} target="_blank" rel="noopener noreferrer nofollow" style={S.a}>{children}</a>
  ),
  img: () => null,   // 이미지 비활성(외부 로드·트래킹·레이아웃 깨짐 방지)
  p: ({ children }) => <p style={S.p}>{children}</p>,
  ul: ({ children }) => <ul style={S.ul}>{children}</ul>,
  ol: ({ children }) => <ol style={S.ol}>{children}</ol>,
  li: ({ children }) => <li style={S.li}>{children}</li>,
  h1: ({ children }) => <h1 style={S.h('1.2em')}>{children}</h1>,
  h2: ({ children }) => <h2 style={S.h('1.1em')}>{children}</h2>,
  h3: ({ children }) => <h3 style={S.h('1.05em')}>{children}</h3>,
  h4: ({ children }) => <h4 style={S.h('1em')}>{children}</h4>,
  h5: ({ children }) => <h5 style={S.h('1em')}>{children}</h5>,
  h6: ({ children }) => <h6 style={S.h('1em')}>{children}</h6>,
  code: ({ className, children }) => {
    const block = /language-/.test(className || '') || String(children).includes('\n')
    return <code style={block ? S.codeBlock : S.codeInline}>{children}</code>
  },
  pre: ({ children }) => <pre style={S.pre}>{children}</pre>,
  blockquote: ({ children }) => <blockquote style={S.bq}>{children}</blockquote>,
  table: ({ children }) => <div style={S.tableWrap}><table style={S.table}>{children}</table></div>,
  th: ({ children }) => <th style={S.th}>{children}</th>,
  td: ({ children }) => <td style={S.td}>{children}</td>,
  hr: () => <hr style={S.hr} />,
}

/**
 * AI(assistant) 챗버블용 마크다운 렌더러.
 * - raw HTML 미파싱(react-markdown 기본 — rehype-raw 안 씀)
 * - 이미지 비활성, 링크는 새 탭·rel 보안·프로토콜 화이트리스트
 * - GFM(취소선·자동링크·태스크리스트·테이블), 테이블은 가로 스크롤로 담음
 * 스트리밍 중 미완성 구문은 react-markdown이 리터럴로 보이다 닫히면 서식으로 스냅한다.
 */
export default function Markdown({ children }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={safeUrl} components={components}>
      {children || ''}
    </ReactMarkdown>
  )
}
