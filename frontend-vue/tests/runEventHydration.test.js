import test from 'node:test'
import assert from 'node:assert/strict'

import { collectRunEventPages } from '../src/utils/runEventHydration.js'

test('collectRunEventPages exhaustively loads all event pages for initial hydration', async () => {
  const calls = []
  const events = await collectRunEventPages(async (afterSequence, limit) => {
    calls.push({ afterSequence, limit })
    if (afterSequence === 0) {
      return [{ sequence: 1 }, { sequence: 2 }]
    }
    if (afterSequence === 2) {
      return [{ sequence: 3 }, { sequence: 4 }]
    }
    if (afterSequence === 4) {
      return [{ sequence: 5 }]
    }
    return []
  }, {
    afterSequence: 0,
    limit: 2,
    exhaustive: true
  })

  assert.deepEqual(events.map((event) => event.sequence), [1, 2, 3, 4, 5])
  assert.deepEqual(calls, [
    { afterSequence: 0, limit: 2 },
    { afterSequence: 2, limit: 2 },
    { afterSequence: 4, limit: 2 }
  ])
})

test('collectRunEventPages keeps incremental hydration single-page when exhaustive is disabled', async () => {
  const calls = []
  const events = await collectRunEventPages(async (afterSequence, limit) => {
    calls.push({ afterSequence, limit })
    return [{ sequence: 11 }, { sequence: 12 }]
  }, {
    afterSequence: 10,
    limit: 2,
    exhaustive: false
  })

  assert.deepEqual(events.map((event) => event.sequence), [11, 12])
  assert.deepEqual(calls, [{ afterSequence: 10, limit: 2 }])
})
