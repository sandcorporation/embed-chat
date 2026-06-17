const { test, expect, request } = require('@playwright/test')

const WIDGET_URL = process.env.WIDGET_URL || 'http://localhost:5173'
const API_URL = process.env.API_URL || 'http://localhost:8000'

async function getEmbedToken() {
  const apiContext = await request.newContext({ baseURL: API_URL })

  const opRes = await apiContext.post('/api/operator/auth/login', {
    data: {
      username: process.env.E2E_OPERATOR_USERNAME || 'admin',
      password: process.env.E2E_OPERATOR_PASSWORD || 'admin123',
    },
  })
  const { access_token: opToken } = await opRes.json()

  const tenantRes = await apiContext.post('/api/operator/tenants/', {
    headers: { Authorization: `Bearer ${opToken}` },
    data: { name: `Widget E2E Tenant ${Date.now()}` },
  })
  const tenant = await tenantRes.json()

  // 에이전트 로그인 후 모델 설정
  const agentRes = await apiContext.post('/api/tenant/agents/auth/login', {
    data: {
      tenant_name: tenant.name,
      username: tenant.agent_username,
      password: tenant.agent_temp_password,
    },
  })
  const { access_token: agentToken } = await agentRes.json()

  await apiContext.patch('/api/tenant/config/', {
    headers: { Authorization: `Bearer ${agentToken}` },
    data: { model_id: 'qwen2.5:3b' },
  })

  const embedRes = await apiContext.post('/api/embed/token', {
    headers: { Authorization: `Bearer ${tenant.tenant_key}` },
    data: { visitor_id: 'e2e-visitor-001', visitor_context: {} },
  })
  const { embed_token } = await embedRes.json()
  await apiContext.dispose()

  return embed_token
}

test.describe('Widget 채팅 플로우', () => {
  let embedToken

  test.beforeAll(async () => {
    embedToken = await getEmbedToken()
  })

  test('위젯이 로드되고 연결 대기 상태로 시작한다', async ({ page }) => {
    await page.goto(`${WIDGET_URL}/embed/?token=${embedToken}`)
    const textarea = page.locator('textarea[placeholder="메시지를 입력하세요..."]')
    await expect(textarea).toBeVisible({ timeout: 10000 })
  })

  test('SSE 연결 후 메시지 입력이 활성화된다', async ({ page }) => {
    await page.goto(`${WIDGET_URL}/embed/?token=${embedToken}`)
    const textarea = page.locator('textarea[placeholder="메시지를 입력하세요..."]')
    await expect(textarea).toBeEnabled({ timeout: 10000 })
  })

  test('메시지 전송 후 AI 응답이 표시된다', async ({ page }) => {
    await page.goto(`${WIDGET_URL}/embed/?token=${embedToken}`)
    const textarea = page.locator('textarea[placeholder="메시지를 입력하세요..."]')
    await expect(textarea).toBeEnabled({ timeout: 10000 })

    await textarea.fill('안녕하세요')
    await page.click('button:has-text("전송")')

    await expect(page.locator('[data-role="user"]')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('[data-role="assistant"]')).toBeVisible({ timeout: 30000 })
  })
})
