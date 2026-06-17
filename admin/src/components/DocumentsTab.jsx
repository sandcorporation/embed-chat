import React, { useState, useEffect, useRef } from 'react'
import { listDocuments, uploadDocument, updateDocument, deleteDocument, queryDocuments, listDocumentChunks } from '../api'
import { s } from '../styles'

const STATUS_COLORS = { pending: '#ed8936', processing: '#4299e1', ready: '#48bb78', failed: '#fc8181' }

export default function DocumentsTab({ agentToken }) {
  const [docs, setDocs] = useState([])
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef()
  const [pendingFile, setPendingFile] = useState(null)   // 업로드 대기 중인 File
  const [uploadLabel, setUploadLabel] = useState('')      // 업로드 모달의 레이블 값
  const [editingId, setEditingId] = useState(null)        // 인라인 편집 중인 문서 id
  const [editLabel, setEditLabel] = useState('')
  const [ragQuery, setRagQuery] = useState('')
  const [ragTopK, setRagTopK] = useState(5)
  const [ragResults, setRagResults] = useState(null)
  const [ragLoading, setRagLoading] = useState(false)
  const [expandedChunks, setExpandedChunks] = useState({})  // docId → chunks[] | 'loading'

  const runRagQuery = async (q) => {
    if (!q.trim()) return
    setRagLoading(true)
    const results = await queryDocuments(agentToken, q, ragTopK)
    setRagResults(results)
    setRagLoading(false)
  }

  const load = async () => {
    const data = await listDocuments(agentToken)
    setDocs(data)
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 3000)
    return () => clearInterval(interval)
  }, [])

  const handleFileSelect = (e) => {
    const file = e.target.files[0]
    if (!file) return
    setPendingFile(file)
    setUploadLabel(file.name)  // 파일명을 레이블 기본값으로 미리 채움
  }

  const cancelUpload = () => {
    setPendingFile(null)
    setUploadLabel('')
    if (fileRef.current) fileRef.current.value = ''
  }

  const confirmUpload = async () => {
    if (!pendingFile) return
    setUploading(true)
    await uploadDocument(agentToken, pendingFile, uploadLabel.trim())
    await load()
    setUploading(false)
    cancelUpload()
  }

  const startEdit = (doc) => {
    setEditingId(doc.id)
    setEditLabel(doc.name)
  }

  const saveEdit = async (id) => {
    const name = editLabel.trim()
    if (!name) return
    await updateDocument(agentToken, id, name)
    setEditingId(null)
    setEditLabel('')
    await load()
  }

  const handleDelete = async (id) => {
    if (!confirm('삭제하시겠습니까?')) return
    await deleteDocument(agentToken, id)
    setExpandedChunks(prev => { const n = { ...prev }; delete n[id]; return n })
    await load()
  }

  const toggleChunks = async (docId) => {
    if (expandedChunks[docId] !== undefined) {
      setExpandedChunks(prev => { const n = { ...prev }; delete n[docId]; return n })
      return
    }
    setExpandedChunks(prev => ({ ...prev, [docId]: 'loading' }))
    const chunks = await listDocumentChunks(agentToken, docId)
    setExpandedChunks(prev => ({ ...prev, [docId]: chunks }))
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.txt,.png,.jpg,.jpeg,.webp"
          onChange={handleFileSelect}
          style={{ display: 'none' }}
          id="file-upload"
        />
        <label htmlFor="file-upload" style={s.btn}>
          {uploading ? '업로드 중...' : '📄 문서 업로드 (PDF/TXT/이미지)'}
        </label>
        <span style={{ fontSize: 13, color: '#718096' }}>3초마다 상태 자동 갱신</span>
      </div>

      {pendingFile && (
        <div style={{
          marginBottom: 16, padding: 16, border: '1px solid #90cdf4',
          borderRadius: 8, background: '#ebf8ff',
        }} data-testid="upload-modal">
          <label style={s.label}>Document Label (제품명·모델명으로 지정하면 검색이 정확해집니다)</label>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              data-testid="upload-label-input"
              style={{ ...s.input, flex: 1 }}
              value={uploadLabel}
              onChange={e => setUploadLabel(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && confirmUpload()}
            />
            <button
              data-testid="upload-confirm"
              style={s.btn}
              onClick={confirmUpload}
              disabled={uploading || !uploadLabel.trim()}
            >
              {uploading ? '업로드 중...' : '업로드'}
            </button>
            <button style={s.btnDanger} onClick={cancelUpload} disabled={uploading}>취소</button>
          </div>
          <div style={{ fontSize: 12, color: '#718096', marginTop: 6 }}>{pendingFile.name}</div>
        </div>
      )}

      <table style={s.table}>
        <thead>
          <tr>
            <th style={s.th}>파일명</th>
            <th style={s.th}>상태</th>
            <th style={s.th}>작업</th>
          </tr>
        </thead>
        <tbody>
          {docs.map(d => (
            <React.Fragment key={d.id}>
              <tr>
                <td style={s.td}>
                  {editingId === d.id ? (
                    <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <input
                        data-testid="edit-label-input"
                        style={{ ...s.input, padding: '4px 8px', fontSize: 13 }}
                        value={editLabel}
                        onChange={e => setEditLabel(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && saveEdit(d.id)}
                        autoFocus
                      />
                      <button
                        data-testid="save-label"
                        style={{ ...s.btnSm, padding: '4px 10px' }}
                        onClick={() => saveEdit(d.id)}
                      >저장</button>
                      <button
                        style={{ ...s.btnDanger, padding: '4px 10px' }}
                        onClick={() => { setEditingId(null); setEditLabel('') }}
                      >취소</button>
                    </span>
                  ) : (
                    <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      {d.name}
                      <button
                        data-testid="edit-label"
                        title="레이블 수정"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 13, color: '#4299e1', padding: 0 }}
                        onClick={() => startEdit(d)}
                      >✏️ 레이블 수정</button>
                    </span>
                  )}
                </td>
                <td style={s.td}>
                  <span style={{ color: STATUS_COLORS[d.status], fontWeight: 600 }}>{d.status}</span>
                  {d.error_message && <span style={{ marginLeft: 8, fontSize: 12, color: '#fc8181' }}>{d.error_message}</span>}
                </td>
                <td style={s.td}>
                  <button
                    style={{ ...s.btn, fontSize: 12, padding: '3px 8px', marginRight: 6 }}
                    onClick={() => toggleChunks(d.id)}
                    data-testid={`chunks-toggle-${d.id}`}
                  >
                    {expandedChunks[d.id] !== undefined ? '청크 닫기' : '청크 보기'}
                  </button>
                  <button style={s.btnDanger} onClick={() => handleDelete(d.id)}>삭제</button>
                </td>
              </tr>
              {expandedChunks[d.id] !== undefined && (
                <tr>
                  <td colSpan={3} style={{ ...s.td, background: '#f7fafc', padding: 0 }}>
                    <div style={{ padding: 12 }} data-testid={`chunks-panel-${d.id}`}>
                      {expandedChunks[d.id] === 'loading' && (
                        <div style={{ color: '#718096', fontSize: 13 }}>청크 로딩 중...</div>
                      )}
                      {Array.isArray(expandedChunks[d.id]) && expandedChunks[d.id].length === 0 && (
                        <div style={{ color: '#a0aec0', fontSize: 13 }}>청크 없음</div>
                      )}
                      {Array.isArray(expandedChunks[d.id]) && expandedChunks[d.id].map(c => (
                        <div key={c.chunk_index} data-testid="chunk-item" style={{ marginBottom: 8, fontSize: 12, borderBottom: '1px solid #e2e8f0', paddingBottom: 8 }}>
                          <span style={{ fontWeight: 700, color: '#4299e1', marginRight: 8 }}>#{c.chunk_index}</span>
                          <span data-testid="chunk-content" style={{ color: '#4a5568' }}>{c.content.slice(0, 200)}{c.content.length > 200 ? '…' : ''}</span>
                        </div>
                      ))}
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
          {docs.length === 0 && (
            <tr><td colSpan={3} style={{ ...s.td, textAlign: 'center', color: '#a0aec0' }}>문서가 없습니다</td></tr>
          )}
        </tbody>
      </table>

      <div style={{ marginTop: 32, borderTop: '1px solid #e2e8f0', paddingTop: 24 }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12, color: '#2d3748' }}>RAG 테스트</h3>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center' }}>
          <input
            style={{ ...s.input, flex: 1 }}
            placeholder="검색어를 입력하세요"
            value={ragQuery}
            onChange={e => setRagQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && runRagQuery(e.target.value)}
          />
          <input
            type="number"
            min={1}
            max={20}
            style={{ ...s.input, width: 60 }}
            value={ragTopK}
            onChange={e => setRagTopK(Number(e.target.value))}
            title="top_k"
          />
          <button style={s.btn} onClick={() => runRagQuery(ragQuery)} disabled={ragLoading}>
            {ragLoading ? '검색 중...' : '검색'}
          </button>
        </div>
        <div style={{ fontSize: 12, color: '#718096', marginBottom: 12 }}>
          점수(낮을수록 유사)
        </div>

        {ragLoading && <div style={{ color: '#718096' }}>검색 중...</div>}

        {ragResults !== null && !ragLoading && ragResults.length === 0 && (
          <div style={{ color: '#a0aec0', textAlign: 'center', padding: 16 }}>결과 없음</div>
        )}

        {ragResults !== null && ragResults.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {ragResults.map((r, i) => (
              <div key={i} style={{ border: '1px solid #e2e8f0', borderRadius: 6, padding: 12, background: '#f7fafc' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{r.document_name}</span>
                  <span data-testid="rag-score" style={{ fontSize: 12, color: '#718096' }}>{r.score.toFixed(4)}</span>
                </div>
                <div style={{ fontSize: 13, color: '#4a5568', whiteSpace: 'pre-wrap' }}>{r.content}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
