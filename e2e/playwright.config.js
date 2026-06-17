const { defineConfig } = require('@playwright/test')

const ADMIN_URL = process.env.ADMIN_URL || 'http://localhost:5174'
const WIDGET_URL = process.env.WIDGET_URL || 'http://localhost:5173'
const API_URL = process.env.API_URL || 'http://localhost:8000'

module.exports = defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 0,
  globalSetup: require.resolve('./global-setup'),
  use: {
    headless: true,
    baseURL: ADMIN_URL,
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
})

// Export URLs for use in tests
module.exports.ADMIN_URL = ADMIN_URL
module.exports.WIDGET_URL = WIDGET_URL
module.exports.API_URL = API_URL
