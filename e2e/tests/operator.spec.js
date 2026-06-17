const { test, expect } = require('@playwright/test')

const ADMIN_URL = process.env.ADMIN_URL || 'http://localhost:5174'

test.describe('Operator 플로우', () => {
  test.beforeEach(async ({ page }) => {
    // 매 테스트 전 localStorage 초기화
    await page.goto(`${ADMIN_URL}/admin-ui/`)
    await page.evaluate(() => localStorage.clear())
  })

  test('Operator 로그인 성공', async ({ page }) => {
    await page.goto(`${ADMIN_URL}/admin-ui/operator`)

    await page.fill('input[placeholder="아이디"]', process.env.E2E_OPERATOR_USERNAME || 'admin')
    await page.fill('input[placeholder="비밀번호"]', process.env.E2E_OPERATOR_PASSWORD || 'admin123')
    await page.click('button[type="submit"]')

    // 로그인 후 테넌트 목록 화면으로 이동
    await expect(page.locator('text=Tenant 목록')).toBeVisible({ timeout: 5000 })
  })

  test('잘못된 자격증명으로 에러 메시지 표시', async ({ page }) => {
    await page.goto(`${ADMIN_URL}/admin-ui/operator`)

    await page.fill('input[placeholder="아이디"]', 'wrong')
    await page.fill('input[placeholder="비밀번호"]', 'wrong')
    await page.click('button[type="submit"]')

    await expect(page.locator('text=아이디 또는 비밀번호가 올바르지 않습니다.')).toBeVisible()
  })

  test('Operator가 새 테넌트를 생성할 수 있다', async ({ page }) => {
    await page.goto(`${ADMIN_URL}/admin-ui/operator`)
    await page.fill('input[placeholder="아이디"]', process.env.E2E_OPERATOR_USERNAME || 'admin')
    await page.fill('input[placeholder="비밀번호"]', process.env.E2E_OPERATOR_PASSWORD || 'admin123')
    await page.click('button[type="submit"]')
    await expect(page.locator('text=Tenant 목록')).toBeVisible()

    const tenantName = `E2E 테스트 테넌트 ${Date.now()}`
    await page.fill('input[placeholder="고객사 이름"]', tenantName)
    await page.click('button:has-text("추가")')

    await expect(page.locator(`text=${tenantName}`).first()).toBeVisible({ timeout: 5000 })
  })
})
