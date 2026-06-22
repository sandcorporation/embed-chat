import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getTenantConfig, updateTenantConfig, resetTenantKey, updateTenantSlug, fetchProviderModels } from '../api'
import type { TenantConfigOut } from '../generated/model'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Select } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type DaySchedule = { enabled?: boolean; start?: string; end?: string }
const WEEKDAYS: [string, string][] = [
  ['mon', '월'], ['tue', '화'], ['wed', '수'], ['thu', '목'], ['fri', '금'], ['sat', '토'], ['sun', '일'],
]

function modelOptions(loaded: string[], current: string, extra: string[] = []): string[] {
  return Array.from(new Set([...extra, ...loaded, current].filter(Boolean)))
}

const POPULAR_MODELS = [
  'openrouter/owl-alpha', 'openai/gpt-4o', 'openai/gpt-4o-mini',
  'anthropic/claude-3-5-sonnet', 'anthropic/claude-3-haiku',
  'google/gemini-flash-1.5', 'meta-llama/llama-3.1-8b-instruct:free',
]
const WEBHOOK_TYPES = [
  { value: '', label: '없음' }, { value: 'slack', label: 'Slack' },
  { value: 'discord', label: 'Discord' }, { value: 'generic', label: 'Generic' },
]
const SECTIONS = [
  { id: 'general', label: '일반', intro: '봇이 손님에게 어떻게 보이고 말하는지 정합니다.' },
  { id: 'ai', label: 'AI 모델', intro: '챗봇을 움직이는 AI 엔진을 고릅니다. 가장 기술적인 부분이라, 모르면 담당 개발자와 함께 설정하세요.' },
  { id: 'handoff', label: '상담 전환', intro: 'AI가 답하기 어려울 때 사람 상담원에게 넘기는 방식을 정합니다.' },
  { id: 'security', label: '공개 URL·보안', intro: '챗봇 공개 주소와 접근 보안을 관리합니다.' },
]

const hint = 'mt-1 text-xs text-muted-foreground'
const errorCls = 'mt-1 text-sm text-destructive'

export default function ConfigTab() {
  const [searchParams, setSearchParams] = useSearchParams()
  const section = searchParams.get('section') || 'general'
  const setSection = (id: string) => setSearchParams({ section: id }, { replace: true })

  const [config, setConfig] = useState<TenantConfigOut>({
    model_id: '', system_prompt: '', agent_display_name: '상담원',
    webhook_url: '', webhook_type: '', welcome_message: '',
  } as unknown as TenantConfigOut)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [newKey, setNewKey] = useState<string | null>(null)
  const [resetConfirm, setResetConfirm] = useState(false)
  const [slug, setSlug] = useState('')
  const [slugSaved, setSlugSaved] = useState(false)
  const [llmModels, setLlmModels] = useState<string[]>([])
  const [embedModels, setEmbedModels] = useState<string[]>([])
  const [ocrModels, setOcrModels] = useState<string[]>([])
  const [llmModelError, setLlmModelError] = useState('')
  const [embedModelError, setEmbedModelError] = useState('')
  const [ocrModelError, setOcrModelError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [holidayInput, setHolidayInput] = useState('')

  const schedule = ((config as TenantConfigOut).hitl_schedule || {}) as Record<string, DaySchedule>
  const holidays = ((config as TenantConfigOut).hitl_holidays || []) as string[]
  const setDay = (key: string, patch: DaySchedule) =>
    setConfig(c => {
      const sched = ((c as TenantConfigOut).hitl_schedule || {}) as Record<string, DaySchedule>
      return { ...c, hitl_schedule: { ...sched, [key]: { ...(sched[key] || {}), ...patch } } } as TenantConfigOut
    })
  const addHoliday = (d: string) => {
    if (d && !holidays.includes(d)) setConfig(c => ({ ...c, hitl_holidays: [...holidays, d] }) as TenantConfigOut)
  }
  const removeHoliday = (d: string) =>
    setConfig(c => ({ ...c, hitl_holidays: holidays.filter(x => x !== d) }) as TenantConfigOut)

  const loadLlmModels = async () => {
    setLlmModelError('')
    try {
      setLlmModels(await fetchProviderModels('llm', config.llm_provider_type, config.llm_base_url, config.llm_api_key, config.model_id))
    } catch { setLlmModelError('LLM 모델 조회 실패 — Base URL / API Key를 확인하세요') }
  }
  const loadEmbedModels = async () => {
    setEmbedModelError('')
    try {
      setEmbedModels(await fetchProviderModels('embed', config.embed_provider_type, config.embed_base_url, config.embed_api_key, config.embed_model))
    } catch { setEmbedModelError('Embedding 모델 조회 실패 — Base URL / API Key를 확인하세요') }
  }
  const loadOcrModels = async () => {
    setOcrModelError('')
    try {
      setOcrModels(await fetchProviderModels('ocr', config.ocr_provider_type, config.ocr_base_url, config.ocr_api_key, config.ocr_model))
    } catch { setOcrModelError('OCR 모델 조회 실패 — Base URL / API Key를 확인하세요') }
  }
  const handleSaveSlug = async () => {
    try {
      await updateTenantSlug(slug)
      setSlugSaved(true)
      setTimeout(() => setSlugSaved(false), 2000)
    } catch (e) { alert(e instanceof Error ? e.message : String(e)) }
  }

  useEffect(() => {
    getTenantConfig().then(data => { setConfig(data); setLoading(false) })
  }, [])

  const handleSave = async () => {
    setSaveError('')
    try {
      await updateTenantConfig(config)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch { setSaveError('저장 실패 — Provider 연결 검증에 실패했을 수 있습니다(Base URL / API Key 확인)') }
  }
  const handleResetKey = async () => {
    if (!resetConfirm) { setResetConfirm(true); return }
    try {
      const data = await resetTenantKey()
      setNewKey(data.new_tenant_key)
      setResetConfirm(false)
    } catch { alert('재발급에 실패했습니다.'); setResetConfirm(false) }
  }

  if (loading) return <p className="text-sm text-muted-foreground">로딩 중...</p>

  const intro = SECTIONS.find(s => s.id === section)?.intro

  return (
    <div className="max-w-3xl">
      <div role="tablist" className="mb-1 flex gap-1 border-b border-border">
        {SECTIONS.map(s => (
          <button key={s.id} role="tab" aria-selected={section === s.id} onClick={() => setSection(s.id)}
            className={cn('-mb-px border-b-2 px-3 py-2 text-sm transition-colors',
              section === s.id ? 'border-primary font-medium text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground')}>
            {s.label}
          </button>
        ))}
      </div>
      {intro && <p className="mb-5 mt-3 text-xs text-muted-foreground">{intro}</p>}

      {/* ── 일반 ─────────────────────────────────────────── */}
      {section === 'general' && (
        <div className="space-y-6">
          <div className="space-y-2">
            <Label>브랜드 텍스트</Label>
            <Input aria-label="브랜드 텍스트" value={config.brand_name || ''}
              onChange={e => setConfig(c => ({ ...c, brand_name: e.target.value }))}
              placeholder="위젯 헤더 상단에 표시 (비우면 상태 텍스트만)" />
            <p className={hint}>위젯 상단에 보일 가게/서비스 이름이에요.</p>
          </div>
          <div className="space-y-2">
            <Label>환영 메시지</Label>
            <Textarea value={config.welcome_message}
              onChange={e => setConfig(c => ({ ...c, welcome_message: e.target.value }))}
              placeholder="위젯이 열릴 때 방문자에게 표시될 메시지 (비워두면 표시 안 함)" />
            <p className={hint}>위젯이 열릴 때 손님에게 보여줄 첫인사예요.</p>
          </div>
          <div className="space-y-2">
            <Label>Base System Prompt</Label>
            <Textarea data-testid="system-prompt-input" className="min-h-[200px] font-mono text-xs"
              value={config.system_prompt} onChange={e => setConfig(c => ({ ...c, system_prompt: e.target.value }))} />
            <p className={hint}>봇의 성격·말투·역할을 정하는 지시문이에요. 예: "친절한 쇼핑몰 상담원처럼 존댓말로 답하라."</p>
          </div>
          <div className="space-y-2">
            <Label>상담원 표시 이름</Label>
            <Input value={config.agent_display_name}
              onChange={e => setConfig(c => ({ ...c, agent_display_name: e.target.value }))} placeholder="상담원" />
            <p className={hint}>사람 상담원으로 전환됐을 때 손님에게 보일 이름이에요.</p>
          </div>
        </div>
      )}

      {/* ── AI 모델 ───────────────────────────────────────── */}
      {section === 'ai' && (
        <div className="space-y-6">
          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-semibold">LLM Provider (비용 부담)</h3>
              <p className="text-xs text-muted-foreground">손님과 대화하고 자료를 정리하는 핵심 AI예요. {config.platform_default_providers_enabled ? '미설정 시 플랫폼 기본(OpenRouter)을 씁니다.' : '프로덕션에선 LLM Provider 설정이 필수입니다.'}</p>
            </div>
            <div className="space-y-2">
              <Label>LLM Provider 타입</Label>
              <Select aria-label="LLM Provider 타입" value={config.llm_provider_type || ''}
                onChange={e => { const v = e.target.value; setConfig(c => ({ ...c, llm_provider_type: v, llm_base_url: v === 'custom' ? c.llm_base_url : '' })) }}>
                {config.platform_default_providers_enabled && <option value="">기본 (OpenRouter)</option>}
                <option value="openai">OpenAI</option>
                <option value="anthropic">Claude (Anthropic)</option>
                <option value="custom">Custom (OpenAI-호환)</option>
              </Select>
              <p className={hint}>어떤 AI 회사 서비스를 쓸지 골라요(OpenAI·Claude 등). "기본"은 플랫폼이 제공하는 모델이에요.</p>
            </div>
            {config.llm_provider_type === 'custom' && (
              <div className="space-y-2">
                <Label>LLM Base URL</Label>
                <Input aria-label="LLM Base URL" value={config.llm_base_url || ''}
                  onChange={e => setConfig(c => ({ ...c, llm_base_url: e.target.value }))} placeholder="예: https://openrouter.ai/api/v1" />
                <p className={hint}>Custom(직접 호스팅·기타 서비스)일 때만 그 주소를 넣어요.</p>
              </div>
            )}
            <div className="space-y-2">
              <Label>LLM API Key</Label>
              <Input type="password" aria-label="LLM API Key" value={config.llm_api_key || ''}
                onChange={e => setConfig(c => ({ ...c, llm_api_key: e.target.value }))} placeholder="설정됨이면 ******** (변경할 때만 입력)" />
              <p className={hint}>AI 서비스에서 발급받은 비밀 키예요. 모르면 담당 개발자에게 "OpenAI(또는 Claude) API 키"라고 요청하세요.</p>
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
              <Select aria-label="AI 모델" value={config.model_id} onChange={e => setConfig(c => ({ ...c, model_id: e.target.value }))}>
                {modelOptions(llmModels, config.model_id, POPULAR_MODELS).map(m => <option key={m} value={m}>{m}</option>)}
              </Select>
              <Input aria-label="AI 모델 직접 입력" className="text-xs" value={config.model_id}
                onChange={e => setConfig(c => ({ ...c, model_id: e.target.value }))} placeholder="직접 입력(목록에 없는 모델)" />
              <p className={hint}>손님과 대화하고, 올린 자료도 이 AI가 정리합니다.</p>
            </div>
            <Button type="button" variant="ghost" size="sm" className="px-0 text-muted-foreground hover:bg-transparent"
              onClick={() => setShowAdvanced(v => !v)}>{showAdvanced ? '▾' : '▸'} 고급 설정</Button>
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
            <div>
              <h3 className="text-sm font-semibold">Embedding Provider</h3>
              <p className="text-xs text-muted-foreground">올린 문서를 AI가 검색하도록 "숫자 지문"으로 바꾸는 엔진이에요. 보통 LLM과 같은 회사 걸 쓰면 됩니다. 프로덕션에선 설정 필수.</p>
            </div>
            <div className="space-y-2">
              <Label>Embedding Provider 타입</Label>
              <Select aria-label="Embedding Provider 타입" value={config.embed_provider_type || ''}
                onChange={e => { const v = e.target.value; setConfig(c => ({ ...c, embed_provider_type: v, embed_base_url: v === 'custom' ? c.embed_base_url : '' })) }}>
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
                onChange={e => setConfig(c => ({ ...c, embed_api_key: e.target.value }))} placeholder="설정됨이면 ******** (변경할 때만 입력)" />
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
              <p className={hint}>임베딩 모델이 만드는 "숫자 지문"의 길이예요. 모델 기본값을 쓰면 됩니다(예: 1024).</p>
            </div>
          </div>

          <div className="space-y-4 border-t border-border pt-6">
            <div>
              <h3 className="text-sm font-semibold">OCR(Vision) Provider</h3>
              <p className="text-xs text-muted-foreground">이미지·스캔 PDF의 글자를 읽어들이는 vision 모델이에요(예: GPT-4o, Claude, Gemini). 미설정 시 개발 환경은 Paddle로 대체하고, 프로덕션에선 설정해야 이미지·스캔 문서를 올릴 수 있어요.</p>
            </div>
            <div className="space-y-2">
              <Label>OCR Provider 타입</Label>
              <Select aria-label="OCR Provider 타입" value={config.ocr_provider_type || ''}
                onChange={e => { const v = e.target.value; setConfig(c => ({ ...c, ocr_provider_type: v, ocr_base_url: v === 'custom' ? c.ocr_base_url : '' })) }}>
                <option value="">(미설정)</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic (Claude)</option>
                <option value="custom">Custom (OpenAI-호환)</option>
              </Select>
            </div>
            {config.ocr_provider_type === 'custom' && (
              <div className="space-y-2">
                <Label>OCR Base URL</Label>
                <Input aria-label="OCR Base URL" value={config.ocr_base_url || ''}
                  onChange={e => setConfig(c => ({ ...c, ocr_base_url: e.target.value }))} />
              </div>
            )}
            <div className="space-y-2">
              <Label>OCR API Key</Label>
              <Input type="password" aria-label="OCR API Key" value={config.ocr_api_key || ''}
                onChange={e => setConfig(c => ({ ...c, ocr_api_key: e.target.value }))} placeholder="설정됨이면 ******** (변경할 때만 입력)" />
            </div>
            <div>
              <Button size="sm" variant="outline" type="button" onClick={loadOcrModels}>OCR 모델 불러오기</Button>
              {ocrModelError && <p className={errorCls}>{ocrModelError}</p>}
            </div>
            <div className="space-y-2">
              <Label>OCR 모델</Label>
              <Select aria-label="OCR 모델" value={config.ocr_model || ''}
                onChange={e => setConfig(c => ({ ...c, ocr_model: e.target.value }))}>
                <option value="">(선택)</option>
                {modelOptions(ocrModels, config.ocr_model).map(m => <option key={m} value={m}>{m}</option>)}
              </Select>
              <Input aria-label="OCR 모델 직접 입력" className="text-xs" value={config.ocr_model || ''}
                onChange={e => setConfig(c => ({ ...c, ocr_model: e.target.value }))} placeholder="직접 입력(vision 가능 모델)" />
            </div>
          </div>
        </div>
      )}

      {/* ── 상담 전환(HITL) ───────────────────────────────── */}
      {section === 'handoff' && (
        <div className="space-y-6">
          <div>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4 rounded border-input" checked={!!config.hitl_enabled}
                onChange={e => setConfig(c => ({ ...c, hitl_enabled: e.target.checked }))} />
              HITL 사용
            </label>
            <p className={hint}>끄면 AI 전용으로 운영되며 상담원 전환(escalation)이 발생하지 않습니다.</p>
          </div>
          <div className="space-y-2">
            <Label>웹훅 유형</Label>
            <Select aria-label="웹훅 유형 선택" value={config.webhook_type}
              onChange={e => setConfig(c => ({ ...c, webhook_type: e.target.value }))}>
              {WEBHOOK_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </Select>
            <p className={hint}>상담 요청이 생기면 Slack/Discord 등으로 알림을 보낼 곳이에요(선택).</p>
          </div>
          {config.webhook_type && (
            <div className="space-y-2">
              <Label>웹훅 URL</Label>
              <Input value={config.webhook_url} onChange={e => setConfig(c => ({ ...c, webhook_url: e.target.value }))}
                placeholder="https://hooks.slack.com/..." />
            </div>
          )}

          {/* ── 상담 가능 시간(영업시간) ─ HITL 켜진 경우에만 ── */}
          {config.hitl_enabled && (
            <div className="space-y-4 border-t border-border pt-6">
              <div>
                <h3 className="text-sm font-semibold">상담 가능 시간 (영업시간)</h3>
                <p className="text-xs text-muted-foreground">상담원이 응대 가능한 요일·시간이에요. 이 시간 외에는 AI만 답하고 상담원 자동 연결은 일어나지 않습니다. 비워두면 24시간 항상 연결돼요.</p>
              </div>
              <div className="space-y-2">
                <Label>표준시간대 (타임존)</Label>
                <Input aria-label="타임존" className="w-64" value={config.hitl_timezone || ''}
                  onChange={e => setConfig(c => ({ ...c, hitl_timezone: e.target.value }))} placeholder="예: Asia/Seoul" />
                <p className={hint}>시간을 어느 지역 기준으로 볼지예요. 한국이면 Asia/Seoul.</p>
              </div>
              <div className="space-y-1.5">
                <Label>요일별 시간</Label>
                {WEEKDAYS.map(([key, label]) => {
                  const day = schedule[key] || {}
                  return (
                    <div key={key} className="flex items-center gap-2 text-sm">
                      <label className="flex w-14 cursor-pointer items-center gap-1.5">
                        <input type="checkbox" aria-label={`${label} 영업`} className="h-4 w-4 rounded border-input"
                          checked={!!day.enabled} onChange={e => setDay(key, { enabled: e.target.checked })} />
                        {label}
                      </label>
                      <Input aria-label={`${label} 시작`} type="time" className="w-32" value={day.start || ''}
                        disabled={!day.enabled} onChange={e => setDay(key, { start: e.target.value })} />
                      <span className="text-muted-foreground">~</span>
                      <Input aria-label={`${label} 종료`} type="time" className="w-32" value={day.end || ''}
                        disabled={!day.enabled} onChange={e => setDay(key, { end: e.target.value })} />
                    </div>
                  )
                })}
              </div>
              <div className="space-y-2">
                <Label>휴일 (쉬는 날)</Label>
                <div className="flex items-center gap-2">
                  <Input aria-label="휴일 추가" type="date" className="w-44" value={holidayInput}
                    onChange={e => setHolidayInput(e.target.value)} />
                  <Button size="sm" variant="outline" type="button"
                    onClick={() => { addHoliday(holidayInput); setHolidayInput('') }}>추가</Button>
                </div>
                {holidays.length > 0 && (
                  <ul className="flex flex-wrap gap-1.5">
                    {holidays.map(d => (
                      <li key={d}>
                        <Badge variant="secondary" className="gap-1">{d}
                          <button type="button" aria-label={`휴일 ${d} 삭제`} className="ml-1 leading-none"
                            onClick={() => removeHoliday(d)}>×</button>
                        </Badge>
                      </li>
                    ))}
                  </ul>
                )}
                <p className={hint}>공휴일·정기휴무처럼 요일과 상관없이 쉬는 날이에요. 그날은 상담원 연결이 꺼집니다.</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── 공개 URL·보안 ─────────────────────────────────── */}
      {section === 'security' && (
        <div className="space-y-6">
          <div className="space-y-2">
            <Label>Tenant Slug (공개 챗봇 URL)</Label>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">/chatbot/</span>
              <Input aria-label="Tenant Slug" className="w-64" value={slug} onChange={e => setSlug(e.target.value)}
                placeholder="abc-shop (소문자·숫자·하이픈)" />
              <span className="text-sm text-muted-foreground">/</span>
              <Button size="sm" variant="outline" onClick={handleSaveSlug}>{slugSaved ? '✓ 저장됨' : 'Slug 저장'}</Button>
            </div>
            <p className={hint}>손님이 접속하는 공개 챗봇 주소의 일부예요. 변경하면 사이트에 박아둔 기존 임베드 URL이 끊깁니다.</p>
          </div>
          <div>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4 rounded border-input" aria-label="visitor_id 신원검증 요구"
                checked={!!config.require_identity_verification}
                onChange={e => setConfig(c => ({ ...c, require_identity_verification: e.target.checked }))} />
              visitor_id 신원검증 요구 (HMAC)
            </label>
            <p className={hint}>켜면 식별 방문자는 HMAC 해시가 있어야 연결됩니다(위조 방지). 익명은 영향 없음. 모르면 꺼두세요.</p>
          </div>
          <div className="space-y-3 border-t border-border pt-6">
            <div>
              <h3 className="text-sm font-semibold">API KEY 재발급</h3>
              <p className="text-xs text-muted-foreground">서버 연동용 비밀 키예요. 재발급 즉시 기존 KEY는 무효화되니 서버 설정을 바로 업데이트해야 합니다.</p>
            </div>
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
      )}

      {/* 항상 보이는 atomic 저장 (Slug 저장·키 재발급은 별도) */}
      <div className="mt-8 space-y-2 border-t border-border pt-6">
        {saveError && <p className={errorCls}>{saveError}</p>}
        <Button onClick={handleSave}>{saved ? '✓ 저장됨' : '저장'}</Button>
        <p className={hint}>모든 탭의 변경을 한 번에 저장합니다.</p>
      </div>
    </div>
  )
}
