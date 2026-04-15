import test from 'node:test'
import assert from 'node:assert/strict'

import { buildRunEventPatch, deriveRunState } from '../src/utils/agentRunState.js'

test('deriveRunState rebuilds only the latest execution surface after run.resumed', () => {
  const baseRun = {
    id: 'run-1',
    plan: { action: { type: 'tool_call', title: 'Old plan' } },
    finalOutput: 'old answer',
    finalOutputText: 'old answer',
    finalOutputJson: { answer: 'old answer' },
    artifacts: [
      {
        artifactType: 'citations',
        name: 'Old Sources',
        payload: { items: [{ title: 'Old Source', url: 'https://example.com/old' }] }
      }
    ],
    steps: [
      {
        id: 'step-old',
        stepIndex: 1,
        kind: 'tool_call',
        title: 'Old step',
        status: 'completed',
        createdAt: '2026-04-01T10:00:00.000Z',
        updatedAt: '2026-04-01T10:00:01.000Z'
      }
    ],
    toolCalls: [
      {
        id: 'tool-old',
        stepId: 'step-old',
        toolName: 'search_old',
        toolKind: 'mcp',
        status: 'completed',
        result: {
          structured_content: {
            citations: [{ title: 'Old Source', url: 'https://example.com/old' }]
          }
        },
        createdAt: '2026-04-01T10:00:00.000Z',
        updatedAt: '2026-04-01T10:00:01.000Z'
      }
    ]
  }

  const events = [
    {
      id: 'event-1',
      eventType: 'run.completed',
      createdAt: '2026-04-01T10:00:02.000Z',
      payload: {
        final_output: 'old answer',
        final_output_text: 'old answer',
        final_output_json: { answer: 'old answer' },
        artifacts: [
          {
            artifact_type: 'citations',
            name: 'Old Sources',
            payload: { items: [{ title: 'Old Source', url: 'https://example.com/old' }] }
          }
        ]
      }
    },
    {
      id: 'event-2',
      eventType: 'run.resumed',
      createdAt: '2026-04-01T10:01:00.000Z',
      payload: { status: 'queued' }
    },
    {
      id: 'event-3',
      eventType: 'plan.created',
      createdAt: '2026-04-01T10:01:01.000Z',
      payload: {
        plan: {
          action: { type: 'final_answer', title: 'Return answer' },
          reasoning: 'Use the latest attempt only.'
        }
      }
    },
    {
      id: 'event-4',
      eventType: 'tool.started',
      createdAt: '2026-04-01T10:01:02.000Z',
      payload: {
        step_id: 'step-new',
        tool_call_id: 'tool-new',
        tool_name: 'search_docs',
        tool_kind: 'mcp',
        arguments: { query: 'latest' }
      }
    },
    {
      id: 'event-5',
      eventType: 'tool.completed',
      createdAt: '2026-04-01T10:01:03.000Z',
      payload: {
        step_id: 'step-new',
        tool_call_id: 'tool-new',
        tool_name: 'search_docs',
        tool_kind: 'mcp',
        result: {
          structured_content: {
            citations: [{ title: 'New Source', url: 'https://example.com/new' }]
          }
        }
      }
    }
  ]

  const derived = deriveRunState(baseRun, events)

  assert.equal(derived.plan.action.title, 'Return answer')
  assert.deepEqual(derived.steps, [])
  assert.equal(derived.toolCalls.length, 1)
  assert.equal(derived.toolCalls[0].id, 'tool-new')
  assert.equal(derived.artifacts.length, 1)
  assert.equal(derived.artifacts[0].artifactType, 'citations')
  assert.equal(derived.artifacts[0].payload.items[0].title, 'New Source')
})

test('buildRunEventPatch preserves derived artifacts when final event carries only partial explicit artifacts', () => {
  const currentRun = {
    id: 'run-2',
    finalOutput: 'Audit compatibility drift\nBackfill hydration coverage',
    finalOutputText: 'Audit compatibility drift\nBackfill hydration coverage',
    finalOutputJson: {
      steps: [
        { title: 'Audit compatibility drift', status: 'in_progress' },
        { title: 'Backfill hydration coverage', status: 'pending' }
      ]
    },
    toolCalls: [],
    artifacts: [
      {
        artifactType: 'answer',
        name: 'Final Answer',
        payload: { text: 'Audit compatibility drift\nBackfill hydration coverage', format: 'markdown' }
      },
      {
        artifactType: 'task_plan',
        name: 'Task Plan',
        payload: {
          summary: '',
          steps: [
            { title: 'Audit compatibility drift', status: 'in_progress' },
            { title: 'Backfill hydration coverage', status: 'pending' }
          ],
          decisions: []
        }
      }
    ]
  }

  const patch = buildRunEventPatch(currentRun, {
    runId: 'run-2',
    eventType: 'run.completed',
    createdAt: '2026-04-01T10:02:00.000Z',
    payload: {
      status: 'completed',
      final_output_text: 'Audit compatibility drift\nBackfill hydration coverage',
      final_output_json: {
        steps: [
          { title: 'Audit compatibility drift', status: 'in_progress' },
          { title: 'Backfill hydration coverage', status: 'pending' }
        ]
      },
      artifacts: [
        {
          artifact_type: 'citations',
          name: 'Runtime Sources',
          payload: {
            items: [{ title: 'Runtime Plan', url: 'https://example.com/runtime-plan' }]
          }
        }
      ]
    }
  })

  assert.equal(patch.status, 'completed')
  assert.ok(Array.isArray(patch.artifacts))
  assert.deepEqual(
    patch.artifacts.map((artifact) => artifact.artifactType),
    ['answer', 'citations', 'task_plan']
  )
})

test('buildRunEventPatch for waiting_user keeps question text and promoted artifacts together', () => {
  const patch = buildRunEventPatch({
    id: 'run-3',
    finalOutput: '',
    finalOutputText: '',
    finalOutputJson: null,
    context: {},
    toolCalls: [],
    artifacts: []
  }, {
    runId: 'run-3',
    eventType: 'run.waiting_user',
    createdAt: '2026-04-01T10:03:00.000Z',
    payload: {
      status: 'waiting_user',
      question: 'Which environment should I use?',
      artifacts: [
        {
          artifact_type: 'document_excerpt',
          name: 'search_docs - Preview',
          payload: {
            items: [{ title: 'Context', text: 'Production configuration is missing.', source: '' }]
          }
        }
      ]
    }
  })

  assert.equal(patch.finalOutputText, 'Which environment should I use?')
  assert.deepEqual(
    patch.artifacts.map((artifact) => artifact.artifactType),
    ['answer', 'document_excerpt']
  )
})

test('buildRunEventPatch for subagent waiting_user preserves clarification context from event stream', () => {
  const patch = buildRunEventPatch({
    id: 'run-3b',
    finalOutput: '',
    finalOutputText: '',
    finalOutputJson: null,
    context: {
      conversation: [{ role: 'user', content: 'Review the rollout plan' }]
    },
    toolCalls: [],
    artifacts: []
  }, {
    runId: 'run-3b',
    eventType: 'run.waiting_user',
    createdAt: '2026-04-01T10:03:30.000Z',
    payload: {
      status: 'waiting_user',
      question: 'Need the migration rollout window.',
      final_output_json: {
        source: 'subagent_waiting_user',
        question: 'Need the migration rollout window.'
      },
      context_patch: {
        pending_question: 'Need the migration rollout window.',
        pending_subagent_clarification: {
          child_run_id: 'child-run-1',
          question: 'Need the migration rollout window.',
          target: {
            slug: 'review-specialist',
            name: 'Review Specialist'
          },
          clarification: {
            protocol_version: 'managed-subagent.clarification.v1',
            state: 'required',
            required_fields: ['migration rollout window']
          }
        }
      },
      artifacts: []
    }
  })

  assert.equal(patch.finalOutputText, 'Need the migration rollout window.')
  assert.equal(patch.finalOutputJson.source, 'subagent_waiting_user')
  assert.equal(patch.context.pending_question, 'Need the migration rollout window.')
  assert.equal(patch.context.pending_subagent_clarification.child_run_id, 'child-run-1')
  assert.equal(patch.context.conversation[0].content, 'Review the rollout plan')
})

test('buildRunEventPatch for run.resumed clears stale waiting-user context', () => {
  const patch = buildRunEventPatch({
    id: 'run-3c',
    finalOutput: 'Need the migration rollout window.',
    finalOutputText: 'Need the migration rollout window.',
    finalOutputJson: {
      source: 'subagent_waiting_user',
      question: 'Need the migration rollout window.'
    },
    context: {
      conversation: [{ role: 'user', content: 'Review the rollout plan' }],
      pending_question: 'Need the migration rollout window.',
      pending_subagent_clarification: {
        child_run_id: 'child-run-1',
        question: 'Need the migration rollout window.'
      },
      ask_user_guard: { attempt: 1 }
    },
    toolCalls: [],
    artifacts: []
  }, {
    runId: 'run-3c',
    eventType: 'run.resumed',
    createdAt: '2026-04-01T10:04:00.000Z',
    payload: { status: 'queued' }
  })

  assert.equal(patch.finalOutputText, '')
  assert.deepEqual(patch.context, {
    conversation: [{ role: 'user', content: 'Review the rollout plan' }]
  })
})

test('deriveRunState preserves pending subagent clarification context from persisted snapshot', () => {
  const derived = deriveRunState({
    id: 'run-subagent-waiting',
    status: 'waiting_user',
    context: {
      pending_subagent_clarification: {
        child_run_id: 'child-run-1',
        target: {
          slug: 'review-specialist',
          name: 'Review Specialist'
        },
        question: 'Need the migration rollout window.',
        progress: {
          protocol_version: 'managed-subagent.progress.v1',
          state: 'blocked',
          summary: 'Review is blocked pending rollout details.'
        },
        clarification: {
          protocol_version: 'managed-subagent.clarification.v1',
          state: 'required',
          question: 'Need the migration rollout window.',
          required_fields: ['migration rollout window'],
          response_hint: 'Provide the approved rollout window and blackout constraints.'
        },
        governance_policy: {
          protocol_version: 'managed-subagent.governance.v1',
          target_slug: 'review-specialist',
          waiting_user: {
            propagation: 'bubble_to_parent'
          },
          limits: {
            timeout_seconds: 45
          }
        }
      }
    },
    finalOutputText: 'Need the migration rollout window.',
    finalOutputJson: {
      source: 'subagent_waiting_user',
      question: 'Need the migration rollout window.'
    },
    artifacts: [],
    steps: [],
    toolCalls: []
  }, [])

  assert.equal(derived.runPatch.finalOutputText, 'Need the migration rollout window.')
  assert.equal(derived.surfaceMeta.source, 'persisted_snapshot')
})

test('buildRunEventPatch rebuilds structured result surfaces for failed terminal snapshots', () => {
  const patch = buildRunEventPatch({
    id: 'run-4',
    finalOutput: '',
    finalOutputText: '',
    finalOutputJson: null,
    toolCalls: [],
    artifacts: []
  }, {
    runId: 'run-4',
    eventType: 'run.failed',
    createdAt: '2026-04-01T10:04:00.000Z',
    payload: {
      status: 'failed',
      error: 'Synthesis failed',
      final_output_json: {
        steps: [
          { title: 'Audit compatibility drift', status: 'in_progress' },
          { title: 'Backfill replay coverage', status: 'pending' }
        ]
      },
      artifacts: [
        {
          artifact_type: 'citations',
          name: 'Runtime Sources',
          payload: {
            items: [{ title: 'Runtime Plan', url: 'https://example.com/runtime-plan' }]
          }
        }
      ]
    }
  })

  assert.equal(patch.status, 'failed')
  assert.equal(patch.errorMessage, 'Synthesis failed')
  assert.deepEqual(
    patch.artifacts.map((artifact) => artifact.artifactType),
    ['answer', 'citations', 'task_plan']
  )
})

test('deriveRunState exposes persisted snapshot surface metadata when event history is empty', () => {
  const derived = deriveRunState({
    id: 'run-5',
    status: 'failed',
    finalOutputJson: {
      document_pages: {
        title: 'Catalog Export',
        pages: [
          { page: 1, text: '第一页摘要。' },
          { page: 2, text: '第二页摘要。' }
        ]
      }
    },
    artifacts: [],
    steps: [],
    toolCalls: []
  }, [])

  assert.equal(derived.surfaceMeta.source, 'persisted_snapshot')
  assert.equal(derived.surfaceMeta.hasEmptyEventHistory, true)
  assert.equal(derived.surfaceMeta.attemptIndex, 1)
  assert.equal(derived.artifacts.some((artifact) => artifact.artifactType === 'document_pages'), true)
})
