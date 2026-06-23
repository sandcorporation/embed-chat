import { useState, useMemo, useRef } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

// 지식그래프 데모 — 실제 viz 라이브러리(react-force-graph)를 목업 데이터로 구동(admin이 쓰는 그것).
// 노드를 클릭하면 목업 이웃을 머지해 그래프가 확장되는 모습을 연출한다.

interface KGNode { id: string; entity_type: string; description: string }
interface KGEdge { source: string; target: string }

// common-sense 예시: 무선 이어폰 제품 지식그래프.
const SEED: { nodes: KGNode[]; edges: KGEdge[] } = {
  nodes: [
    { id: '제품 설명서', entity_type: 'document', description: '무선 이어폰 사용 설명서' },
    { id: '무선 이어폰', entity_type: 'product', description: '블루투스 무선 이어폰' },
    { id: '배터리', entity_type: 'feature', description: '한 번 충전으로 최대 6시간 재생' },
    { id: '노이즈 캔슬링', entity_type: 'feature', description: '주변 소음을 줄여주는 ANC' },
    { id: '방수', entity_type: 'feature', description: '생활 방수 지원' },
  ],
  edges: [
    { source: '제품 설명서', target: '무선 이어폰' },
    { source: '무선 이어폰', target: '배터리' },
    { source: '무선 이어폰', target: '노이즈 캔슬링' },
    { source: '무선 이어폰', target: '방수' },
  ],
}

// 노드 확장 시 머지할 목업 이웃.
const NEIGHBORS: Record<string, { nodes: KGNode[]; edges: KGEdge[] }> = {
  '배터리': {
    nodes: [{ id: '충전 케이스', entity_type: 'feature', description: '케이스 포함 최대 24시간' }],
    edges: [{ source: '배터리', target: '충전 케이스' }],
  },
  '노이즈 캔슬링': {
    nodes: [{ id: '주변 소리 모드', entity_type: 'feature', description: '외부 소리를 들려주는 모드' }],
    edges: [{ source: '노이즈 캔슬링', target: '주변 소리 모드' }],
  },
  '방수': {
    nodes: [{ id: 'IPX4 등급', entity_type: 'spec', description: '땀·생활 방수 등급' }],
    edges: [{ source: '방수', target: 'IPX4 등급' }],
  },
}

export default function KGDemo() {
  const [nodes, setNodes] = useState<KGNode[]>(SEED.nodes)
  const [edges, setEdges] = useState<KGEdge[]>(SEED.edges)
  const [selected, setSelected] = useState<KGNode | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null)

  const expand = (id: string) => {
    setSelected(nodes.find(n => n.id === id) || null)
    const nb = NEIGHBORS[id]
    if (!nb) return
    setNodes(prev => {
      const seen = new Set(prev.map(n => n.id))
      return [...prev, ...nb.nodes.filter(n => !seen.has(n.id))]
    })
    setEdges(prev => {
      const seen = new Set(prev.map(e => `${e.source}->${e.target}`))
      return [...prev, ...nb.edges.filter(e => !seen.has(`${e.source}->${e.target}`))]
    })
  }

  const graphData = useMemo(
    () => ({ nodes: nodes.map(n => ({ ...n })), links: edges.map(e => ({ ...e })) }),
    [nodes, edges]
  )

  return (
    <div className="kg">
      <div className="kg-graph">
        <ForceGraph2D
          ref={fgRef}
          graphData={graphData}
          nodeLabel="id"
          nodeAutoColorBy="entity_type"
          linkColor={() => '#cbd5e1'}
          linkDirectionalArrowLength={3}
          width={520}
          height={360}
          minZoom={0.8}
          maxZoom={4}
          cooldownTicks={80}
          onEngineStop={() => fgRef.current?.zoomToFit(400, 40)}
          onNodeClick={(n: { id?: string | number }) => expand(String(n.id))}
        />
      </div>
      <div className="kg-panel">
        <div className="kg-count">엔티티 {nodes.length}개 · 관계 {edges.length}개 · 노드를 눌러 펼쳐보세요</div>
        <div className="kg-list">
          {nodes.map(n => (
            <button key={n.id} className="kg-node" data-testid="kg-node" onClick={() => expand(n.id)}>
              <span>{n.id}</span>
              <span className="kg-type">{n.entity_type}</span>
            </button>
          ))}
        </div>
        {selected && (
          <div className="kg-detail" data-testid="kg-detail">
            <div className="kg-detail-name">{selected.id}</div>
            <div className="kg-type">{selected.entity_type}</div>
            <div className="kg-detail-desc">{selected.description}</div>
          </div>
        )}
      </div>
    </div>
  )
}
