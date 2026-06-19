import { defineConfig } from 'orval'

// admin HTTP 클라이언트를 백엔드 OpenAPI에서 생성한다 (ADR-0014).
// 모든 생성 함수는 custom mutator(customInstance)를 거쳐 인증·refresh를 운반한다.
export default defineConfig({
  admin: {
    input: './openapi.json',
    output: {
      mode: 'tags-split',
      target: './src/generated/endpoints',
      schemas: './src/generated/model',
      client: 'fetch',
      override: {
        mutator: { path: './src/mutator.ts', name: 'customInstance' },
      },
    },
  },
})
