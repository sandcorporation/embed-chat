import { useState, useMemo } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

// 지식그래프 데모 — 실제 viz 라이브러리(react-force-graph)를 목업 데이터로 구동(admin이 쓰는 그것).
// 노드를 클릭하면 목업 이웃을 머지해 그래프가 확장되는 모습을 연출한다.

interface KGNode { id: string; entity_type: string; description: string }
interface KGEdge { source: string; target: string }

const SEED: { nodes: KGNode[]; edges: KGEdge[] } = {
  nodes: [
    { id: 'FCB1010 매뉴얼', entity_type: 'document', description: '제품 사용 설명서' },
    { id: 'FCB1010', entity_type: 'product', description: 'MIDI 풋 컨트롤러' },
    { id: '풋스위치', entity_type: 'feature', description: '10개의 할당 가능한 풋스위치' },
    { id: '익스프레션 페달', entity_type: 'feature', description: '2개의 익스프레션 페달 입력' },
  ],
  edges: [
    { source: 'FCB1010 매뉴얼', target: 'FCB1010' },
    { source: 'FCB1010', target: '풋스위치' },
    { source: 'FCB1010', target: '익스프레션 페달' },
  ],
}

// 노드 확장 시 머지할 목업 이웃.
const NEIGHBORS: Record<string, { nodes: KGNode[]; edges: KGEdge[] }> = {
  '풋스위치': {
    nodes: [{ id: 'MIDI 프로그램 체인지', entity_type: 'feature', description: '풋스위치별 PC 송출' }],
    edges: [{ source: '풋스위치', target: 'MIDI 프로그램 체인지' }],
  },
  '익스프레션 페달': {
    nodes: [{ id: 'CC 컨트롤', entity_type: 'feature', description: '익스프레션으로 연속 제어' }],
    edges: [{ source: '익스프레션 페달', target: 'CC 컨트롤' }],
  },
}

export default function KGDemo() {
  const [nodes, setNodes] = useState<KGNode[]>(SEED.nodes)
  const [edges, setEdges] = useState<KGEdge[]>(SEED.edges)
  const [selected, setSelected] = useState<KGNode | null>(null)

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
          graphData={graphData}
          nodeLabel="id"
          nodeAutoColorBy="entity_type"
          linkDirectionalArrowLength={4}
          width={520}
          height={360}
          onNodeClick={(n: { id?: string | number }) => expand(String(n.id))}
        />
      </div>
      <div className="kg-panel">
        <div className="kg-count">엔티티 {nodes.length}개 · 관계 {edges.length}개</div>
        <div className="kg-list">
          {nodes.map(n => (
            <button key={n.id} className="kg-node" data-testid="kg-node" onClick={() => expand(n.id)}>
              {n.id} <span className="kg-type">{n.entity_type}</span>
            </button>
          ))}
        </div>
        {selected && (
          <div className="kg-detail" data-testid="kg-detail">
            <div className="kg-detail-name">{selected.id}</div>
            <div className="kg-type">{selected.entity_type}</div>
            <div>{selected.description}</div>
          </div>
        )}
      </div>
    </div>
  )
}
