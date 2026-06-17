import { useState, useEffect } from 'react'
import { getTenantConfig, updateTenantConfig, resetTenantKey } from '../api'
import { s } from '../styles'

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

export default function ConfigTab({ agentToken }) {
  const [config, setConfig] = useState({
    model_id: '',
    system_prompt: '',
    agent_display_name: '상담원',
    webhook_url: '',
    webhook_type: '',
    welcome_message: '',
  })
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [newKey, setNewKey] = useState(null)
  const [resetConfirm, setResetConfirm] = useState(false)

  useEffect(() => {
    getTenantConfig(agentToken).then(data => {
      setConfig(data)
      setLoading(false)
    })
  }, [])

  const handleSave = async () => {
    await updateTenantConfig(agentToken, config)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const handleResetKey = async () => {
    if (!resetConfirm) {
      setResetConfirm(true)
      return
    }
    try {
      const data = await resetTenantKey(agentToken)
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
      <div style={{ marginBottom: 20 }}>
        <label style={s.label}>LLM 모델</label>
        <select
          aria-label="LLM 모델 선택"
          style={{ ...s.input, width: '100%' }}
          value={config.model_id}
          onChange={e => setConfig(c => ({ ...c, model_id: e.target.value }))}
        >
          {POPULAR_MODELS.map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
          {!POPULAR_MODELS.includes(config.model_id) && (
            <option value={config.model_id}>{config.model_id}</option>
          )}
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
