const { test, expect, request } = require('@playwright/test')

const ADMIN_URL = process.env.ADMIN_URL || 'http://localhost:5174'
const API_URL = process.env.API_URL || 'http://localhost:8000'

async function setup() {
  const api = await request.newContext({ baseURL: API_URL })

  const opRes = await api.post('/api/operator/auth/login', {
    data: {
      username: process.env.E2E_OPERATOR_USERNAME || 'admin',
      password: process.env.E2E_OPERATOR_PASSWORD || 'admin123',
    },
  })
  const { access_token: opToken } = await opRes.json()

  const tenantRes = await api.post('/api/operator/tenants/', {
    headers: { Authorization: `Bearer ${opToken}` },
    data: { name: `RAG Panel E2E ${Date.now()}` },
  })
  const tenant = await tenantRes.json()

  await api.dispose()
  return { tenant }
}

async function loginAsTenantAgent(page, tenant) {
  await page.goto(`${ADMIN_URL}/admin-ui/tenant`)
  await page.fill('input[placeholder="Tenant 이름"]', tenant.name)
  await page.fill('input[placeholder="사용자명"]', tenant.agent_username)
  await page.fill('input[placeholder="비밀번호"]', tenant.agent_temp_password)
  await page.click('button[type="submit"]')
  await expect(page.locator('button:has-text("📄 문서")')).toBeVisible({ timeout: 10000 })
}

async function uploadTextDoc(api, agentToken, content, filename) {
  const { FormData, Blob } = await import('node:buffer').then(() => globalThis)
  const form = new FormData()
  form.append('file', new Blob([content], { type: 'text/plain' }), filename)
  const res = await api.post('/api/tenant/documents/', {
    headers: { Authorization: `Bearer ${agentToken}` },
    multipart: { file: { name: filename, mimeType: 'text/plain', buffer: Buffer.from(content) } },
  })
  return res.json()
}

test.describe('RAG 테스트 패널', () => {
  let tenant

  test.beforeAll(async () => {
    const ctx = await setup()
    tenant = ctx.tenant
  })

  test.beforeEach(async ({ page }) => {
    await page.goto(`${ADMIN_URL}/admin-ui/`)
    await page.evaluate(() => localStorage.clear())
  })

  // ── Tracer Bullet ────────────────────────────────────────────────────────
  test('DocumentsTab에 RAG 쿼리 입력이 존재한다', async ({ page }) => {
    await loginAsTenantAgent(page, tenant)
    // 문서 탭은 기본 탭이므로 별도 클릭 불필요
    await expect(page.locator('input[placeholder*="검색어"]')).toBeVisible({ timeout: 5000 })
  })

  // ── 쿼리 실행 ────────────────────────────────────────────────────────────
  test('문서 업로드 후 관련 쿼리를 실행하면 청크가 결과에 표시된다', async ({ page }) => {
    const api = await request.newContext({ baseURL: API_URL })

    // agent 토큰 취득
    const agentRes = await api.post('/api/tenant/agents/auth/login', {
      data: {
        tenant_name: tenant.name,
        username: tenant.agent_username,
        password: tenant.agent_temp_password,
      },
    })
    const { access_token: agentToken } = await agentRes.json()

    // 문서 업로드
    const ts = Date.now()
    await uploadTextDoc(
      api,
      agentToken,
      `FCB1010 power supply requires 9V DC adapter.`,
      `rag-e2e-${ts}.txt`
    )
    await api.dispose()

    await loginAsTenantAgent(page, tenant)
    // 업로드한 문서가 ready 상태가 될 때까지 대기 (3초 polling + worker 처리)
    const docRow = page.locator('tr', { has: page.locator(`text=rag-e2e-${ts}.txt`) })
    await expect(docRow).toBeVisible({ timeout: 10000 })
    await expect(docRow.locator('text=ready')).toBeVisible({ timeout: 30000 })

    await page.fill('input[placeholder*="검색어"]', 'power supply')
    await page.keyboard.press('Enter')

    await expect(page.locator('text=power supply')).toBeVisible({ timeout: 10000 })
  })

  test('검색 결과에 점수(score)가 숫자로 표시된다', async ({ page }) => {
    const api = await request.newContext({ baseURL: API_URL })

    const agentRes = await api.post('/api/tenant/agents/auth/login', {
      data: {
        tenant_name: tenant.name,
        username: tenant.agent_username,
        password: tenant.agent_temp_password,
      },
    })
    const { access_token: agentToken } = await agentRes.json()

    const ts = Date.now()
    await uploadTextDoc(api, agentToken, `Return policy: 30 days.`, `score-e2e-${ts}.txt`)
    await api.dispose()

    await loginAsTenantAgent(page, tenant)
    const scoreRow = page.locator('tr', { has: page.locator(`text=score-e2e-${ts}.txt`) })
    await expect(scoreRow).toBeVisible({ timeout: 10000 })
    await expect(scoreRow.locator('text=ready')).toBeVisible({ timeout: 30000 })

    await page.fill('input[placeholder*="검색어"]', 'return policy')
    await page.keyboard.press('Enter')

    // score 숫자가 표시되는지 확인 (소수점 포함 숫자 패턴)
    await expect(page.locator('[data-testid="rag-score"]').first()).toBeVisible({ timeout: 10000 })
  })

  test('문서가 없을 때 쿼리를 실행하면 빈 결과 안내가 표시된다', async ({ page }) => {
    // 별도 tenant를 사용해 문서가 없는 환경 보장
    const api = await request.newContext({ baseURL: API_URL })

    const opRes = await api.post('/api/operator/auth/login', {
      data: {
        username: process.env.E2E_OPERATOR_USERNAME || 'admin',
        password: process.env.E2E_OPERATOR_PASSWORD || 'admin123',
      },
    })
    const { access_token: opToken } = await opRes.json()

    const emptyTenantRes = await api.post('/api/operator/tenants/', {
      headers: { Authorization: `Bearer ${opToken}` },
      data: { name: `Empty RAG ${Date.now()}` },
    })
    const emptyTenant = await emptyTenantRes.json()
    await api.dispose()

    await loginAsTenantAgent(page, emptyTenant)
    await page.fill('input[placeholder*="검색어"]', 'anything')
    await page.keyboard.press('Enter')

    await expect(page.locator('text=결과 없음')).toBeVisible({ timeout: 5000 })
  })
})
