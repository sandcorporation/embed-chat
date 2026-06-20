import { useState, useEffect } from 'react'
import { getTenantConfig, updateTenantConfig, resetTenantKey, updateTenantSlug, fetchProviderModels } from '../api'
import type { TenantConfigOut } from '../generated/model'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Select } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

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

const hint = 'mt-1 text-xs text-muted-foreground'
const errorCls = 'mt-1 text-sm text-destructive'

function SectionTitle({ title, desc }: { title: string; desc?: string }) {
  return (
    <div className="space-y-1">
      <h3 className="text-sm font-semibold">{title}</h3>
      {desc && <p className="text-xs text-muted-foreground">{desc}</p>}
    </div>
  )
}

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
  // 조회 에러는 각 provider 섹션에 따로 표시한다(엉뚱한 곳에 뜨지 않도록).
  const [llmModelError, setLlmModelError] = useState('')
  const [embedModelError, setEmbedModelError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)

  const loadLlmModels = async () => {
    setLlmModelError('')
    try {
      setLlmModels(await fetchProviderModels('llm', config.llm_provider_type, config.llm_base_url, config.llm_api_key, config.model_id))
    } catch {
      setLlmModelError('LLM 모델 조회 실패 — Base URL / API Key를 확인하세요')
    }
  }

  const loadEmbedModels = async () => {
    setEmbedModelError('')
    try {
      setEmbedModels(await fetchProviderModels('embed', config.embed_provider_type, config.embed_base_url, config.embed_api_key, config.embed_model))
    } catch {
      setEmbedModelError('Embedding 모델 조회 실패 — Base URL / API Key를 확인하세요')
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

  if (loading) return <p className="text-sm text-muted-foreground">로딩 중...</p>

  return (
    <div className="max-w-3xl space-y-8">
      <div className="space-y-2">
        <Label>Tenant Slug (공개 챗봇 URL)</Label>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">/chatbot/</span>
          <Input aria-label="Tenant Slug" className="w-64" value={slug}
            onChange={e => setSlug(e.target.value)} placeholder="abc-shop (소문자·숫자·하이픈)" />
          <span className="text-sm text-muted-foreground">/</span>
          <Button size="sm" variant="outline" onClick={handleSaveSlug}>{slugSaved ? '✓ 저장됨' : 'Slug 저장'}</Button>
        </div>
        <p className={hint}>변경하면 사이트에 박아둔 기존 임베드 URL이 끊깁니다.</p>
      </div>

      <div className="space-y-2">
        <Label>환영 메시지</Label>
        <Textarea value={config.welcome_message}
          onChange={e => setConfig(c => ({ ...c, welcome_message: e.target.value }))}
          placeholder="위젯이 열릴 때 방문자에게 표시될 메시지 (비워두면 표시 안 함)" />
      </div>

      <div className="space-y-2">
        <Label>브랜드 텍스트</Label>
        <Input aria-label="브랜드 텍스트" value={config.brand_name || ''}
          onChange={e => setConfig(c => ({ ...c, brand_name: e.target.value }))}
          placeholder="위젯 헤더 상단에 표시 (비우면 상태 텍스트만)" />
      </div>

      <div className="space-y-2">
        <Label>Base System Prompt</Label>
        <Textarea data-testid="system-prompt-input" className="min-h-[200px] font-mono text-xs"
          value={config.system_prompt}
          onChange={e => setConfig(c => ({ ...c, system_prompt: e.target.value }))} />
      </div>

      <div className="space-y-4 border-t border-border pt-6">
        <SectionTitle title="HITL 설정" />
        <div>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 rounded border-input"
              checked={!!config.hitl_enabled}
              onChange={e => setConfig(c => ({ ...c, hitl_enabled: e.target.checked }))} />
            HITL 사용
          </label>
          <p className={hint}>끄면 AI 전용으로 운영되며 상담원 전환(escalation)이 발생하지 않습니다.</p>
        </div>
        <div className="space-y-2">
          <Label>상담원 표시 이름</Label>
          <Input value={config.agent_display_name}
            onChange={e => setConfig(c => ({ ...c, agent_display_name: e.target.value }))} placeholder="상담원" />
        </div>
        <div className="space-y-2">
          <Label>웹훅 유형</Label>
          <Select aria-label="웹훅 유형 선택" value={config.webhook_type}
            onChange={e => setConfig(c => ({ ...c, webhook_type: e.target.value }))}>
            {WEBHOOK_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </Select>
        </div>
        {config.webhook_type && (
          <div className="space-y-2">
            <Label>웹훅 URL</Label>
            <Input value={config.webhook_url}
              onChange={e => setConfig(c => ({ ...c, webhook_url: e.target.value }))}
              placeholder="https://hooks.slack.com/..." />
          </div>
        )}
      </div>

      <div className="space-y-4 border-t border-border pt-6">
        <SectionTitle title="접근 / 보안" />
        <div>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 rounded border-input" aria-label="visitor_id 신원검증 요구"
              checked={!!config.require_identity_verification}
              onChange={e => setConfig(c => ({ ...c, require_identity_verification: e.target.checked }))} />
            visitor_id 신원검증 요구 (HMAC)
          </label>
          <p className={hint}>켜면 식별 방문자는 HMAC 해시가 있어야 연결됩니다(위조 방지). 익명은 영향 없음.</p>
        </div>
      </div>

      <div className="space-y-4 border-t border-border pt-6">
        <SectionTitle title="LLM Provider (비용 부담)" desc="미설정 시 플랫폼 기본(OpenRouter)을 사용합니다. 챗·추출에 공용으로 쓰입니다." />
        <div className="space-y-2">
          <Label>LLM Provider 타입</Label>
          <Select aria-label="LLM Provider 타입" value={config.llm_provider_type || ''}
            onChange={e => {
              const v = e.target.value
              setConfig(c => ({ ...c, llm_provider_type: v, llm_base_url: v === 'custom' ? c.llm_base_url : '' }))
            }}>
            {config.platform_default_providers_enabled && <option value="">기본 (OpenRouter)</option>}
            <option value="openai">OpenAI</option>
            <option value="anthropic">Claude (Anthropic)</option>
            <option value="custom">Custom (OpenAI-호환)</option>
          </Select>
        </div>
        {config.llm_provider_type === 'custom' && (
          <div className="space-y-2">
            <Label>LLM Base URL</Label>
            <Input aria-label="LLM Base URL" value={config.llm_base_url || ''}
              onChange={e => setConfig(c => ({ ...c, llm_base_url: e.target.value }))}
              placeholder="예: https://openrouter.ai/api/v1" />
          </div>
        )}
        <div className="space-y-2">
          <Label>LLM API Key</Label>
          <Input type="password" aria-label="LLM API Key" value={config.llm_api_key || ''}
            onChange={e => setConfig(c => ({ ...c, llm_api_key: e.target.value }))}
            placeholder="설정됨이면 ******** (변경할 때만 입력)" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" type="button" onClick={loadLlmModels}>LLM 모델 불러오기</Button>
            <span className="text-xs text-muted-foreground">provider에서 사용가능 모델을 조회해 아래 AI 모델 목록에 채웁니다.</span>
          </div>
          {llmModelError && <p className={errorCls}>{llmModelError}</p>}
        </div>
        <div className="space-y-2">
          <Label>AI 모델</Label>
          <Select aria-label="AI 모델" value={config.model_id}
            onChange={e => setConfig(c => ({ ...c, model_id: e.target.value }))}>
            {modelOptions(llmModels, config.model_id, POPULAR_MODELS).map(m => <option key={m} value={m}>{m}</option>)}
          </Select>
          <Input aria-label="AI 모델 직접 입력" className="text-xs" value={config.model_id}
            onChange={e => setConfig(c => ({ ...c, model_id: e.target.value }))} placeholder="직접 입력(목록에 없는 모델)" />
          <p className={hint}>손님과 대화하고, 올린 자료도 이 AI가 정리합니다.</p>
        </div>
        <Button type="button" variant="ghost" size="sm" className="px-0 text-muted-foreground hover:bg-transparent"
          onClick={() => setShowAdvanced(v => !v)}>
          {showAdvanced ? '▾' : '▸'} 고급 설정
        </Button>
        {showAdvanced && (
          <div className="space-y-2 border-l-2 border-border pl-3">
            <Label>자료 정리 모델</Label>
            <Select aria-label="자료 정리 모델" value={config.extraction_model || ''}
              onChange={e => setConfig(c => ({ ...c, extraction_model: e.target.value }))}>
              <option value="">(대화 모델과 동일)</option>
              {modelOptions(llmModels, config.extraction_model).map(m => <option key={m} value={m}>{m}</option>)}
            </Select>
            <Input aria-label="자료 정리 모델 직접 입력" className="text-xs" value={config.extraction_model || ''}
              onChange={e => setConfig(c => ({ ...c, extraction_model: e.target.value }))} placeholder="비우면 대화 모델과 동일" />
            <p className={hint}>문서를 올릴 때 내용을 정리하는 모델입니다. 보통 비워두면 됩니다.</p>
          </div>
        )}
      </div>

      <div className="space-y-4 border-t border-border pt-6">
        <SectionTitle title="Embedding Provider" desc="LLM과 독립. 변경 시 기존 그래프가 재임베딩됩니다. 프로덕션에선 설정 필수." />
        <div className="space-y-2">
          <Label>Embedding Provider 타입</Label>
          <Select aria-label="Embedding Provider 타입" value={config.embed_provider_type || ''}
            onChange={e => {
              const v = e.target.value
              setConfig(c => ({ ...c, embed_provider_type: v, embed_base_url: v === 'custom' ? c.embed_base_url : '' }))
            }}>
            {config.platform_default_providers_enabled && <option value="">기본 (dev: ollama)</option>}
            <option value="openai">OpenAI</option>
            <option value="custom">Custom (OpenAI-호환)</option>
          </Select>
        </div>
        {config.embed_provider_type === 'custom' && (
          <div className="space-y-2">
            <Label>Embedding Base URL</Label>
            <Input aria-label="Embedding Base URL" value={config.embed_base_url || ''}
              onChange={e => setConfig(c => ({ ...c, embed_base_url: e.target.value }))} />
          </div>
        )}
        <div className="space-y-2">
          <Label>Embedding API Key</Label>
          <Input type="password" aria-label="Embedding API Key" value={config.embed_api_key || ''}
            onChange={e => setConfig(c => ({ ...c, embed_api_key: e.target.value }))}
            placeholder="설정됨이면 ******** (변경할 때만 입력)" />
        </div>
        <div>
          <Button size="sm" variant="outline" type="button" onClick={loadEmbedModels}>Embedding 모델 불러오기</Button>
          {embedModelError && <p className={errorCls}>{embedModelError}</p>}
        </div>
        <div className="space-y-2">
          <Label>Embedding 모델</Label>
          <Select aria-label="Embedding 모델" value={config.embed_model || ''}
            onChange={e => setConfig(c => ({ ...c, embed_model: e.target.value }))}>
            <option value="">(선택)</option>
            {modelOptions(embedModels, config.embed_model).map(m => <option key={m} value={m}>{m}</option>)}
          </Select>
          <Input aria-label="Embedding 모델 직접 입력" className="text-xs" value={config.embed_model || ''}
            onChange={e => setConfig(c => ({ ...c, embed_model: e.target.value }))} placeholder="직접 입력(목록에 없는 모델)" />
        </div>
        <div className="space-y-2">
          <Label>Embedding 차원</Label>
          <Input type="number" aria-label="Embedding 차원" className="w-40" value={config.embed_dim ?? 1024}
            onChange={e => setConfig(c => ({ ...c, embed_dim: Number(e.target.value) }))} />
        </div>
      </div>

      <div className="space-y-2">
        {saveError && <p className={errorCls}>{saveError}</p>}
        <Button onClick={handleSave}>{saved ? '✓ 저장됨' : '저장'}</Button>
      </div>

      <div className="space-y-3 border-t border-border pt-6">
        <SectionTitle title="API KEY 재발급" desc="재발급 즉시 기존 KEY는 무효화됩니다. 서버 연동 설정을 즉시 업데이트해야 합니다." />
        {newKey ? (
          <Card className="border-amber-300 bg-amber-50 dark:bg-amber-950/30">
            <CardContent className="space-y-2 pt-5">
              <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">새 API KEY (지금만 표시됩니다. 반드시 복사하세요.)</p>
              <code className="block break-all text-sm">{newKey}</code>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => navigator.clipboard.writeText(newKey)}>복사</Button>
                <Button size="sm" variant="outline" onClick={() => setNewKey(null)}>확인 완료</Button>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="flex items-center gap-3">
            <Button variant={resetConfirm ? 'destructive' : 'outline'} onClick={handleResetKey}>
              {resetConfirm ? '정말 재발급하시겠습니까? (클릭 시 즉시 실행)' : 'API KEY 재발급'}
            </Button>
            {resetConfirm && <Button size="sm" variant="ghost" onClick={() => setResetConfirm(false)}>취소</Button>}
          </div>
        )}
      </div>
    </div>
  )
}
