import test from 'node:test'
import assert from 'node:assert/strict'

import { REDACTION_MASK, redactRuntimePayload, redactRuntimeText } from '../src/utils/runtimeRedaction.js'

test('redactRuntimePayload masks sensitive object keys and container values', () => {
  const redacted = redactRuntimePayload({
    headers: { Authorization: 'Bearer secret-token' },
    env: { OPENAI_API_KEY: 'sk-1234567890abcdef' },
    nested: { client_secret: 'top-secret' },
    query: 'safe'
  })

  assert.equal(redacted.headers.Authorization, REDACTION_MASK)
  assert.equal(redacted.env.OPENAI_API_KEY, REDACTION_MASK)
  assert.equal(redacted.nested.client_secret, REDACTION_MASK)
  assert.equal(redacted.query, 'safe')
})

test('redactRuntimeText masks common inline secret patterns', () => {
  const redacted = redactRuntimeText('Authorization: Bearer abcdefghijklmnop\napi_key=sk-1234567890abcdef')

  assert.equal(redacted.includes('abcdefghijklmnop'), false)
  assert.equal(redacted.includes('sk-1234567890abcdef'), false)
  assert.equal(redacted.includes(REDACTION_MASK), true)
})
