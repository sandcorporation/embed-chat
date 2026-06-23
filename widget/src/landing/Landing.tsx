import ChatDemo from './ChatDemo'
import KGDemo from './KGDemo'

const FEATURES = [
  { title: '지식그래프 기반 RAG', desc: '문서를 Entity·관계 그래프로 구조화해 더 정확한 근거로 답합니다.' },
  { title: '실시간 토큰 스트리밍', desc: 'AI 답변이 타이핑되듯 토큰 단위로 실시간 흘러나옵니다.' },
  { title: 'HITL 상담 전환', desc: 'AI가 불확실하거나 방문자가 원하면 사람 상담원으로 매끄럽게 전환합니다.' },
  { title: '임베드 위젯', desc: '한 줄 스니펫으로 어떤 웹사이트에도 챗봇을 삽입합니다.' },
]

export default function Landing() {
  return (
    <div className="landing">
      <section className="container hero">
        <div className="hero-copy">
          <div className="eyebrow">EMBED CHAT</div>
          <h1>지식그래프 기반<br />AI 챗봇 플랫폼</h1>
          <p>
            문서를 지식그래프로 구조화해 더 정확하게 답하고, 실시간 스트리밍으로 응답하며,
            필요할 땐 사람 상담원으로 전환합니다. 한 줄이면 어떤 사이트에도 삽입됩니다.
          </p>
          <a className="btn-primary" href="/admin-ui/">운영자 로그인</a>
        </div>
        <div className="hero-demo" data-testid="hero-demo">
          <ChatDemo />
        </div>
      </section>

      <section className="container section">
        <h2>핵심 기능</h2>
        <div className="features">
          {FEATURES.map(f => (
            <div className="feature" key={f.title}>
              <h3>{f.title}</h3>
              <p>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="container section">
        <h2>지식그래프</h2>
        <KGDemo />
      </section>

      <section className="container section">
        <h2>문의</h2>
        <div className="contact">
          <a href="mailto:gksdjf1690@gmail.com">gksdjf1690@gmail.com</a>
          <a href="tel:01024831690">010-2483-1690</a>
        </div>
      </section>

      <footer className="footer">© Embed Chat</footer>
    </div>
  )
}
