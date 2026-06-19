import { useState, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { searchGraph, graphNeighbors } from '../api'
import { s } from '../styles'

// 백엔드 {nodes:[{name,...}], edges:[{source,target,description}]} →
// react-force-graph {nodes:[{id,...}], links:[{source,target,...}]}
function toGraphData(nodes, edges) {
  return {
    nodes: nodes.map(n => ({ id: n.name, ...n })),
    links: edges.map(e => ({ source: e.source, target: e.target, description: e.description })),
  }
}

export default function KnowledgeGraphTab() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [nodes, setNodes] = useState([])   // [{name,type,description,source_document_ids}]
  const [edges, setEdges] = useState([])   // [{source,target,description}]
  const [selected, setSelected] = useState(null)

  const mergeSubgraph = useCallback((subNodes, subEdges) => {
    setNodes(prev => {
      const byName = Object.fromEntries(prev.map(n => [n.name, n]))
      for (const n of subNodes) byName[n.name] = n
      return Object.values(byName)
    })
    setEdges(prev => {
      const seen = new Set(prev.map(e => `${e.source}→${e.target}`))
      const next = [...prev]
      for (const e of subEdges) {
        const k = `${e.source}→${e.target}`
        if (!seen.has(k)) { seen.add(k); next.push(e) }
      }
      return next
    })
  }, [])

  const runSearch = async (q) => {
    if (!q.trim()) return
    setLoading(true)
    const data = await searchGraph(q)
    setNodes(data.nodes || [])
    setEdges(data.edges || [])
    setSelected(null)
    setSearched(true)
    setLoading(false)
  }

  const expandNode = async (name) => {
    setSelected(nodes.find(n => n.name === name) || { name })
    const data = await graphNeighbors(name)
    mergeSubgraph(data.nodes || [], data.edges || [])
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        <input
          data-testid="kg-search"
          style={{ ...s.input, flex: 1 }}
          placeholder="엔티티를 검색하세요 (이름·설명)"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && runSearch(e.target.value)}
        />
        <button style={s.btn} onClick={() => runSearch(query)} disabled={loading}>
          {loading ? '검색 중…' : '검색'}
        </button>
      </div>

      {!searched && (
        <div data-testid="kg-empty" style={{ color: '#a0aec0', textAlign: 'center', padding: 48 }}>
          엔티티를 검색하면 지식그래프가 여기에 표시됩니다.
        </div>
      )}

      {searched && nodes.length === 0 && !loading && (
        <div data-testid="kg-no-results" style={{ color: '#a0aec0', textAlign: 'center', padding: 48 }}>
          일치하는 엔티티가 없습니다.
        </div>
      )}

      {searched && nodes.length > 0 && (
        <div style={{ display: 'flex', gap: 16 }}>
          {/* 그래프 시각화 */}
          <div style={{ flex: 1, border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
            <ForceGraph2D
              graphData={toGraphData(nodes, edges)}
              nodeLabel="name"
              nodeAutoColorBy="entity_type"
              linkDirectionalArrowLength={4}
              width={560}
              height={420}
              onNodeClick={(n) => expandNode(n.id)}
            />
          </div>

          {/* 노드 목록 + 디테일 (e2e/접근성용) */}
          <div style={{ width: 320 }}>
            <div style={{ fontSize: 12, color: '#718096', marginBottom: 6 }}>
              엔티티 {nodes.length}개 · 관계 {edges.length}개
            </div>
            <div style={{ maxHeight: 180, overflowY: 'auto', marginBottom: 12 }}>
              {nodes.map(n => (
                <div
                  key={n.name}
                  data-testid="kg-node"
                  onClick={() => expandNode(n.name)}
                  style={{
                    padding: '6px 10px', cursor: 'pointer', fontSize: 13,
                    borderBottom: '1px solid #f7fafc',
                    background: selected && selected.name === n.name ? '#ebf8ff' : 'transparent',
                  }}
                >
                  {n.name} <span style={{ color: '#a0aec0', fontSize: 11 }}>{n.entity_type}</span>
                </div>
              ))}
            </div>

            {selected && (
              <div data-testid="kg-detail" style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 12, background: '#f7fafc' }}>
                <div data-testid="kg-detail-name" style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{selected.name}</div>
                <div style={{ fontSize: 12, color: '#718096', marginBottom: 6 }}>{selected.entity_type}</div>
                <div style={{ fontSize: 13, color: '#4a5568', whiteSpace: 'pre-wrap' }}>{selected.description}</div>
                {selected.source_document_ids && selected.source_document_ids.length > 0 && (
                  <div style={{ fontSize: 11, color: '#a0aec0', marginTop: 8 }}>
                    출처 문서 {selected.source_document_ids.length}개
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
