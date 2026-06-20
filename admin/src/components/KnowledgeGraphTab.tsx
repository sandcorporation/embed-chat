import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import ForceGraph2D from 'react-force-graph-2d'
import { searchGraph, graphNeighbors } from '../api'
import type { GraphNode, GraphEdge } from '../generated/model'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

// 백엔드 {nodes,edges} → react-force-graph {nodes:[{id,...}], links:[{source,target,...}]}
function toGraphData(nodes: GraphNode[], edges: GraphEdge[]) {
  return {
    nodes: nodes.map(n => ({ id: n.name, ...n })),
    links: edges.map(e => ({ source: e.source, target: e.target, description: e.description })),
  }
}

export default function KnowledgeGraphTab() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState(searchParams.get('entity') || '')
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [nodes, setNodes] = useState<GraphNode[]>([])
  const [edges, setEdges] = useState<GraphEdge[]>([])
  const [selected, setSelected] = useState<GraphNode | null>(null)

  const mergeSubgraph = useCallback((subNodes: GraphNode[], subEdges: GraphEdge[]) => {
    setNodes(prev => {
      const byName: Record<string, GraphNode> = {}
      for (const n of prev) byName[n.name] = n
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

  const runSearch = async (q: string) => {
    if (!q.trim()) return
    setLoading(true)
    setSearchParams({ entity: q }, { replace: true })  // ?entity= 딥링크
    const data = await searchGraph(q)
    setNodes(data.nodes || [])
    setEdges(data.edges || [])
    setSelected(null)
    setSearched(true)
    setLoading(false)
  }

  // ?entity= 로 진입 시 자동 검색(딥링크).
  useEffect(() => {
    const e = searchParams.get('entity')
    if (e) runSearch(e)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const expandNode = async (name: string) => {
    setSelected(nodes.find(n => n.name === name) || { name } as GraphNode)
    const data = await graphNeighbors(name)
    mergeSubgraph(data.nodes || [], data.edges || [])
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Input data-testid="kg-search" className="flex-1" placeholder="엔티티를 검색하세요 (이름·설명)"
          value={query} onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && runSearch(e.currentTarget.value)} />
        <Button onClick={() => runSearch(query)} disabled={loading}>{loading ? '검색 중…' : '검색'}</Button>
      </div>

      {!searched && <div data-testid="kg-empty" className="py-12 text-center text-sm text-muted-foreground">엔티티를 검색하면 지식그래프가 여기에 표시됩니다.</div>}
      {searched && nodes.length === 0 && !loading && <div data-testid="kg-no-results" className="py-12 text-center text-sm text-muted-foreground">일치하는 엔티티가 없습니다.</div>}

      {searched && nodes.length > 0 && (
        <div className="flex gap-4">
          <Card className="flex-1 overflow-hidden">
            <ForceGraph2D graphData={toGraphData(nodes, edges)} nodeLabel="name" nodeAutoColorBy="entity_type"
              linkDirectionalArrowLength={4} width={560} height={420} onNodeClick={(n: any) => expandNode(n.id)} />
          </Card>

          <div className="w-80 space-y-3">
            <div className="text-xs text-muted-foreground">엔티티 {nodes.length}개 · 관계 {edges.length}개</div>
            <div className="max-h-44 overflow-y-auto">
              {nodes.map(n => (
                <button key={n.name} data-testid="kg-node" onClick={() => expandNode(n.name)}
                  className={cn('block w-full border-b border-border px-2.5 py-1.5 text-left text-sm hover:bg-accent',
                    selected?.name === n.name && 'bg-accent')}>
                  {n.name} <span className="text-xs text-muted-foreground">{n.entity_type}</span>
                </button>
              ))}
            </div>
            {selected && (
              <Card data-testid="kg-detail">
                <CardContent className="space-y-1 pt-4">
                  <div data-testid="kg-detail-name" className="text-sm font-bold">{selected.name}</div>
                  <div className="text-xs text-muted-foreground">{selected.entity_type}</div>
                  <div className="whitespace-pre-wrap text-sm text-foreground">{selected.description}</div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
