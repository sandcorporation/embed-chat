/**
 * Playwright global setup: E2E 테스트용 Operator 계정 생성.
 * 백엔드 컨테이너에서 manage.py shell로 실행한 후 API가 준비될 때까지 대기.
 */
const { request } = require('@playwright/test')

const API_URL = process.env.API_URL || 'http://localhost:8000'
const OPERATOR_USERNAME = process.env.E2E_OPERATOR_USERNAME || 'admin'
const OPERATOR_PASSWORD = process.env.E2E_OPERATOR_PASSWORD || 'admin123'

module.exports = async function globalSetup() {
  // Operator 계정이 이미 있으면 통과, 없으면 생성 스크립트가 시작 시 실행됨
  // api-e2e 서비스가 startup command로 create_test_operator를 실행함
  const api = await request.newContext({ baseURL: API_URL })

  // 로그인 확인 (최대 30초 대기)
  for (let i = 0; i < 15; i++) {
    try {
      const res = await api.post('/api/operator/auth/login', {
        data: { username: OPERATOR_USERNAME, password: OPERATOR_PASSWORD },
      })
      if (res.ok()) {
        console.log('[global-setup] Operator login OK')
        await api.dispose()
        return
      }
    } catch (e) {
      // not ready yet
    }
    await new Promise(r => setTimeout(r, 2000))
  }

  await api.dispose()
  throw new Error('E2E global setup: operator login failed after 30s')
}
