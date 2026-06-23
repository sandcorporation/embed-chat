import { Card, CardContent } from '@/components/ui/card'

const FEATURES = [
  { title: '지식그래프 기반 RAG', desc: '문서를 Entity·관계 그래프로 구조화해 더 정확한 근거로 답합니다.' },
  { title: '실시간 토큰 스트리밍', desc: 'AI 답변이 타이핑되듯 토큰 단위로 실시간 흘러나옵니다.' },
  { title: 'HITL 상담 전환', desc: 'AI가 불확실하거나 방문자가 원하면 사람 상담원으로 매끄럽게 전환합니다.' },
  { title: '임베드 위젯', desc: '한 줄 스니펫으로 어떤 웹사이트에도 챗봇을 삽입합니다.' },
]

export default function Landing() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Hero */}
      <section className="mx-auto flex max-w-6xl flex-col gap-12 px-6 py-20 lg:flex-row lg:items-center">
        <div className="flex-1 space-y-6">
          <div className="text-sm font-semibold tracking-wide text-primary">EMBED CHAT</div>
          <h1 className="text-4xl font-bold leading-tight sm:text-5xl">
            지식그래프 기반<br />AI 챗봇 플랫폼
          </h1>
          <p className="max-w-md text-lg text-muted-foreground">
            문서를 지식그래프로 구조화해 더 정확하게 답하고, 실시간 스트리밍으로 응답하며,
            필요할 땐 사람 상담원으로 전환합니다. 한 줄이면 어떤 사이트에도 삽입됩니다.
          </p>
          <a href="/admin-ui/"
             className="inline-flex h-11 items-center rounded-md bg-primary px-6 font-medium text-primary-foreground transition hover:opacity-90">
            운영자 로그인
          </a>
        </div>
        {/* 챗봇 데모 자리 (issue 177에서 실제 ChatWidget + mock 스트리밍으로 채움) */}
        <div className="flex-1" data-testid="hero-demo" />
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <h2 className="mb-10 text-center text-2xl font-bold">핵심 기능</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map(f => (
            <Card key={f.title}>
              <CardContent className="space-y-2 pt-6">
                <div className="font-semibold">{f.title}</div>
                <div className="text-sm text-muted-foreground">{f.desc}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* 지식그래프 데모 자리 (issue 178에서 ForceGraph2D + 목업으로 채움) */}
      <div data-testid="kg-demo-slot" />

      {/* Contact */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <h2 className="mb-6 text-center text-2xl font-bold">문의</h2>
        <div className="flex flex-col items-center gap-3 text-sm">
          <a href="mailto:gksdjf1690@gmail.com" className="text-primary underline">gksdjf1690@gmail.com</a>
          <a href="tel:01024831690" className="text-primary underline">010-2483-1690</a>
        </div>
      </section>

      <footer className="border-t border-border py-8 text-center text-xs text-muted-foreground">
        © Embed Chat
      </footer>
    </div>
  )
}
