import { useState, useEffect } from 'react'
import { getTenantConfig, updateTenantConfig, resetTenantKey, updateTenantSlug, fetchProviderModels } from '../api'
import { s } from '../styles'
import type { TenantConfigOut } from '../generated/model'

// 조회된 모델 + 현재 저장값을 합쳐 중복 없는 옵션 목록을 만든다(저장값 보존).
function modelOptions(loaded: string[], current: string, extra: string[] = []): string[] {
  return Array.from(new Set([...extra, ...loaded, current].filter(Boolean)))
}

const POPULAR_MODELS = [
  'openrouter/owl-alpha',
  'openai/gpt-4o',
  'openai/gpt-4o-mini',
  'anthropic/claude-3-5-sonnet',
  'anthropic/claude-3-haiku',
  'google/gemini-flash-1.5',
  'meta-llama/llama-3.1-8b-instruct:free',
]

const WEBHOOK_TYPES = [
  { value: '', label: '없음' },
  { value: 'slack', label: 'Slack' },
  { value: 'discord', label: 'Discord' },
  { value: 'generic', label: 'Generic' },
]

export default function ConfigTab() {
  const [config, setConfig] = useState<TenantConfigOut>({
    model_id: '',
    system_prompt: '',
    agent_display_name: '상담원',
    webhook_url: '',
    webhook_type: '',
    welcome_message: '',
  } as unknown as TenantConfigOut)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [newKey, setNewKey] = useState<string | null>(null)
  const [resetConfirm, setResetConfirm] = useState(false)
  const [slug, setSlug] = useState('')
  const [slugSaved, setSlugSaved] = useState(false)
  const [llmModels, setLlmModels] = useState<string[]>([])
  const [embedModels, setEmbedModels] = useState<string[]>([])
  const [modelError, setModelError] = useState('')
  const [saveError, setSaveError] = useState('')

  const loadLlmModels = async () => {
    setModelError('')
    try {
      setLlmModels(await fetchProviderModels('llm', config.llm_provider_type, config.llm_base_url, config.llm_api_key, config.model_id))
    } catch {
      setModelError('모델 조회 실패 — Base URL / API Key를 확인하세요')
    }
  }

  const loadEmbedModels = async () => {
    setModelError('')
    try {
      setEmbedModels(await fetchProviderModels('embed', config.embed_provider_type, config.embed_base_url, config.embed_api_key, config.embed_model))
    } catch {
      setModelError('모델 조회 실패 — Base URL / API Key를 확인하세요')
    }
  }

  const handleSaveSlug = async () => {
    try {
      await updateTenantSlug(slug)
      setSlugSaved(true)
      setTimeout(() => setSlugSaved(false), 2000)
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    getTenantConfig().then(data => {
      setConfig(data)
      setLoading(false)
    })
  }, [])

  const handleSave = async () => {
    setSaveError('')
    try {
      await updateTenantConfig(config)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      setSaveError('저장 실패 — Provider 연결 검증에 실패했을 수 있습니다(Base URL / API Key 확인)')
    }
  }

  const handleResetKey = async () => {
    if (!resetConfirm) {
      setResetConfirm(true)
      return
    }
    try {
      const data = await resetTenantKey()
      setNewKey(data.new_tenant_key)
      setResetConfirm(false)
    } catch {
      alert('재발급에 실패했습니다.')
      setResetConfirm(false)
    }
  }

  if (loading) return <p>로딩 중...</p>

  return (
    <div style={{ maxWidth: 700 }}>
      <div style={{ marginBottom: 24 }}>
        <label style={s.label}>Tenant Slug (공개 챗봇 URL)</label>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 13, color: '#718096' }}>/chatbot/</span>
          <input
            aria-label="Tenant Slug"
            style={{ ...s.input, width: 260 }}
            value={slug}
            onChange={e => setSlug(e.target.value)}
            placeholder="abc-shop (소문자·숫자·하이픈)"
          />
          <span style={{ fontSize: 13, color: '#718096' }}>/</span>
          <button style={s.btnSm} onClick={handleSaveSlug}>
            {slugSaved ? '✓ 저장됨' : 'Slug 저장'}
          </button>
        </div>
        <p style={{ marginTop: 4, fontSize: 12, color: '#718096' }}>
          변경하면 사이트에 박아둔 기존 임베드 URL이 끊깁니다.
        </p>
      </div>

      <div style={{ marginBottom: 20 }}>
        <label style={s.label}>LLM 모델</label>
        <select
          aria-label="LLM 모델 선택"
          style={{ ...s.input, width: '100%' }}
          value={config.model_id}
          onChange={e => setConfig(c => ({ ...c, model_id: e.target.value }))}
        >
          {modelOptions(llmModels, config.model_id, POPULAR_MODELS).map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <p style={{ marginTop: 4, fontSize: 12, color: '#718096' }}>
          직접 입력: <input
            style={{ ...s.input, width: 300, marginLeft: 8 }}
            value={config.model_id}
            onChange={e => setConfig(c => ({ ...c, model_id: e.target.value }))}
          />
        </p>
      </div>

      <div style={{ marginBottom: 20 }}>
        <label style={s.label}>환영 메시지</label>
        <textarea
          style={{ ...s.input, width: '100%', minHeight: 60, resize: 'vertical', fontSize: 14 }}
          value={config.welcome_message}
          onChange={e => setConfig(c => ({ ...c, welcome_message: e.target.value }))}
          placeholder="위젯이 열릴 때 방문자에게 표시될 메시지 (비워두면 표시 안 함)"
        />
      </div>

      <div style={{ marginBottom: 20 }}>
        <label style={s.label}>브랜드 텍스트</label>
        <input
          aria-label="브랜드 텍스트"
          style={{ ...s.input, width: '100%' }}
          value={config.brand_name || ''}
          onChange={e => setConfig(c => ({ ...c, brand_name: e.target.value }))}
          placeholder="위젯 헤더 상단에 표시 (비우면 상태 텍스트만)"
        />
      </div>

      <div style={{ marginBottom: 20 }}>
        <label style={s.label}>Base System Prompt</label>
        <textarea
          data-testid="system-prompt-input"
          style={{ ...s.input, width: '100%', minHeight: 200, resize: 'vertical', fontFamily: 'monospace', fontSize: 13 }}
          value={config.system_prompt}
          onChange={e => setConfig(c => ({ ...c, system_prompt: e.target.value }))}
        />
      </div>

      <hr style={{ margin: '24px 0', borderColor: '#e2e8f0' }} />
      <h3 style={{ marginBottom: 16, fontSize: 15, fontWeight: 600 }}>HITL 설정</h3>

      <div style={{ marginBottom: 16 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={!!config.hitl_enabled}
            onChange={e => setConfig(c => ({ ...c, hitl_enabled: e.target.checked }))}
          />
          HITL 사용
        </label>
        <p style={{ marginTop: 4, fontSize: 12, color: '#718096' }}>
          끄면 AI 전용으로 운영되며 상담원 전환(escalation)이 발생하지 않습니다.
        </p>
      </div>

      <div style={{ marginBottom: 16 }}>
        <label style={s.label}>상담원 표시 이름</label>
        <input
          style={{ ...s.input, width: '100%' }}
          value={config.agent_display_name}
          onChange={e => setConfig(c => ({ ...c, agent_display_name: e.target.value }))}
          placeholder="상담원"
        />
      </div>

      <div style={{ marginBottom: 16 }}>
        <label style={s.label}>웹훅 유형</label>
        <select
          aria-label="웹훅 유형 선택"
          style={{ ...s.input, width: '100%' }}
          value={config.webhook_type}
          onChange={e => setConfig(c => ({ ...c, webhook_type: e.target.value }))}
        >
          {WEBHOOK_TYPES.map(t => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      {config.webhook_type && (
        <div style={{ marginBottom: 20 }}>
          <label style={s.label}>웹훅 URL</label>
          <input
            style={{ ...s.input, width: '100%' }}
            value={config.webhook_url}
            onChange={e => setConfig(c => ({ ...c, webhook_url: e.target.value }))}
            placeholder="https://hooks.slack.com/..."
          />
        </div>
      )}

      <hr style={{ margin: '24px 0', borderColor: '#e2e8f0' }} />
      <h3 style={{ marginBottom: 16, fontSize: 15, fontWeight: 600 }}>접근 / 보안</h3>

      <div style={{ marginBottom: 16 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <input
            type="checkbox"
            aria-label="visitor_id 신원검증 요구"
            checked={!!config.require_identity_verification}
            onChange={e => setConfig(c => ({ ...c, require_identity_verification: e.target.checked }))}
          />
          visitor_id 신원검증 요구 (HMAC)
        </label>
        <p style={{ marginTop: 4, fontSize: 12, color: '#718096' }}>
          켜면 식별 방문자는 HMAC 해시가 있어야 연결됩니다(위조 방지). 익명은 영향 없음.
        </p>
      </div>

      <hr style={{ margin: '24px 0', borderColor: '#e2e8f0' }} />
      <h3 style={{ marginBottom: 8, fontSize: 15, fontWeight: 600 }}>LLM Provider (비용 부담)</h3>
      <p style={{ fontSize: 12, color: '#718096', marginBottom: 16 }}>
        미설정 시 플랫폼 기본(OpenRouter)을 사용합니다. 챗·추출에 공용으로 쓰입니다.
      </p>

      <div style={{ marginBottom: 12 }}>
        <label style={s.label}>LLM Provider 타입</label>
        <select
          aria-label="LLM Provider 타입"
          style={{ ...s.input, width: '100%' }}
          value={config.llm_provider_type || ''}
          onChange={e => setConfig(c => ({ ...c, llm_provider_type: e.target.value }))}
        >
          {config.platform_default_providers_enabled && <option value="">기본 (OpenRouter)</option>}
          <option value="openai">OpenAI</option>
          <option value="anthropic">Claude (Anthropic)</option>
          <option value="custom">Custom (OpenAI-호환)</option>
        </select>
      </div>
      <div style={{ marginBottom: 12 }}>
        <label style={s.label}>LLM Base URL</label>
        <input aria-label="LLM Base URL" style={{ ...s.input, width: '100%' }}
          value={config.llm_base_url || ''}
          onChange={e => setConfig(c => ({ ...c, llm_base_url: e.target.value }))}
          placeholder="Custom일 때 (예: https://openrouter.ai/api/v1)" />
      </div>
      <div style={{ marginBottom: 12 }}>
        <label style={s.label}>LLM API Key</label>
        <input type="password" aria-label="LLM API Key" style={{ ...s.input, width: '100%' }}
          value={config.llm_api_key || ''}
          onChange={e => setConfig(c => ({ ...c, llm_api_key: e.target.value }))}
          placeholder="설정됨이면 ******** (변경할 때만 입력)" />
      </div>
      <div style={{ marginBottom: 12 }}>
        <button style={s.btnSm} type="button" onClick={loadLlmModels}>LLM 모델 불러오기</button>
        <span style={{ marginLeft: 8, fontSize: 12, color: '#718096' }}>
          provider에서 사용가능 모델을 조회해 아래 LLM 모델·추출 모델 목록에 채웁니다.
        </span>
      </div>
      <div style={{ marginBottom: 12 }}>
        <label style={s.label}>추출 모델 (비우면 플랫폼 기본)</label>
        <select aria-label="추출 모델" style={{ ...s.input, width: '100%' }}
          value={config.extraction_model || ''}
          onChange={e => setConfig(c => ({ ...c, extraction_model: e.target.value }))}>
          <option value="">(플랫폼 기본)</option>
          {modelOptions(llmModels, config.extraction_model).map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <input aria-label="추출 모델 직접 입력" style={{ ...s.input, width: '100%', marginTop: 4, fontSize: 12 }}
          value={config.extraction_model || ''}
          onChange={e => setConfig(c => ({ ...c, extraction_model: e.target.value }))}
          placeholder="직접 입력(목록에 없는 모델)" />
      </div>

      <hr style={{ margin: '24px 0', borderColor: '#e2e8f0' }} />
      <h3 style={{ marginBottom: 8, fontSize: 15, fontWeight: 600 }}>Embedding Provider</h3>
      <p style={{ fontSize: 12, color: '#718096', marginBottom: 16 }}>
        LLM과 독립. 변경 시 기존 그래프가 재임베딩됩니다. 프로덕션에선 설정 필수.
      </p>

      <div style={{ marginBottom: 12 }}>
        <label style={s.label}>Embedding Provider 타입</label>
        <select
          aria-label="Embedding Provider 타입"
          style={{ ...s.input, width: '100%' }}
          value={config.embed_provider_type || ''}
          onChange={e => setConfig(c => ({ ...c, embed_provider_type: e.target.value }))}
        >
          {config.platform_default_providers_enabled && <option value="">기본 (dev: ollama)</option>}
          <option value="openai">OpenAI</option>
          <option value="custom">Custom (OpenAI-호환)</option>
        </select>
      </div>
      <div style={{ marginBottom: 12 }}>
        <label style={s.label}>Embedding Base URL</label>
        <input aria-label="Embedding Base URL" style={{ ...s.input, width: '100%' }}
          value={config.embed_base_url || ''}
          onChange={e => setConfig(c => ({ ...c, embed_base_url: e.target.value }))} />
      </div>
      <div style={{ marginBottom: 12 }}>
        <label style={s.label}>Embedding API Key</label>
        <input type="password" aria-label="Embedding API Key" style={{ ...s.input, width: '100%' }}
          value={config.embed_api_key || ''}
          onChange={e => setConfig(c => ({ ...c, embed_api_key: e.target.value }))}
          placeholder="설정됨이면 ******** (변경할 때만 입력)" />
      </div>
      <div style={{ marginBottom: 12 }}>
        <button style={s.btnSm} type="button" onClick={loadEmbedModels}>Embedding 모델 불러오기</button>
      </div>
      <div style={{ marginBottom: 12 }}>
        <label style={s.label}>Embedding 모델</label>
        <select aria-label="Embedding 모델" style={{ ...s.input, width: '100%' }}
          value={config.embed_model || ''}
          onChange={e => setConfig(c => ({ ...c, embed_model: e.target.value }))}>
          <option value="">(선택)</option>
          {modelOptions(embedModels, config.embed_model).map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <input aria-label="Embedding 모델 직접 입력" style={{ ...s.input, width: '100%', marginTop: 4, fontSize: 12 }}
          value={config.embed_model || ''}
          onChange={e => setConfig(c => ({ ...c, embed_model: e.target.value }))}
          placeholder="직접 입력(목록에 없는 모델)" />
      </div>
      {modelError && <p style={s.error}>{modelError}</p>}
      <div style={{ marginBottom: 20 }}>
        <label style={s.label}>Embedding 차원</label>
        <input type="number" aria-label="Embedding 차원" style={{ ...s.input, width: 160 }}
          value={config.embed_dim ?? 1024}
          onChange={e => setConfig(c => ({ ...c, embed_dim: Number(e.target.value) }))} />
      </div>

      {saveError && <p style={s.error}>{saveError}</p>}
      <button style={s.btn} onClick={handleSave}>
        {saved ? '✓ 저장됨' : '저장'}
      </button>

      <hr style={{ margin: '32px 0', borderColor: '#e2e8f0' }} />
      <h3 style={{ marginBottom: 8, fontSize: 15, fontWeight: 600 }}>API KEY 재발급</h3>
      <p style={{ fontSize: 13, color: '#718096', marginBottom: 16 }}>
        재발급 즉시 기존 KEY는 무효화됩니다. 서버 연동 설정을 즉시 업데이트해야 합니다.
      </p>

      {newKey ? (
        <div style={{ background: '#fffbeb', border: '1px solid #f6ad55', borderRadius: 8, padding: 16, marginBottom: 12 }}>
          <p style={{ fontSize: 12, color: '#744210', marginBottom: 8, fontWeight: 600 }}>
            새 API KEY (지금만 표시됩니다. 반드시 복사하세요.)
          </p>
          <code style={{ fontSize: 13, wordBreak: 'break-all', display: 'block', marginBottom: 8 }}>{newKey}</code>
          <button style={{ ...s.btnSm, background: '#ed8936', color: '#fff' }} onClick={() => {
            navigator.clipboard.writeText(newKey)
          }}>
            복사
          </button>
          <button style={{ ...s.btnSm, marginLeft: 8 }} onClick={() => setNewKey(null)}>
            확인 완료
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            style={{ ...s.btn, background: resetConfirm ? '#e53e3e' : '#fff', color: resetConfirm ? '#fff' : '#e53e3e', border: '1px solid #e53e3e' }}
            onClick={handleResetKey}
          >
            {resetConfirm ? '정말 재발급하시겠습니까? (클릭 시 즉시 실행)' : 'API KEY 재발급'}
          </button>
          {resetConfirm && (
            <button style={s.btnSm} onClick={() => setResetConfirm(false)}>취소</button>
          )}
        </div>
      )}
    </div>
  )
}
