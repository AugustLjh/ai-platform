import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildInvocationProtocolEntry,
  collectRunTreeInvocations,
  collectRunTreeNodes,
  getInvocationQuestion,
  getInvocationReviewResult,
  normalizeRunTreeNode,
  reviewDecisionLabel,
  summarizeInvocationReview,
  summarizeInvocationTarget,
  summarizeInvocationTask
} from '../src/utils/agentRunTree.js'

test('normalizeRunTreeNode normalizes nested child runs and invocation payloads', () => {
  const root = normalizeRunTreeNode({
    depth: 0,
    run: {
      id: 'run-parent',
      status: 'completed',
      input: { message: 'parent task' },
      final_output_text: 'Parent complete.'
    },
    invocations: [
      {
        invocation: {
          id: 'invocation-1',
          parent_run_id: 'run-parent',
          child_run_id: 'run-child',
          status: 'completed',
          request_payload: {
            task: { message: 'Review the runtime contract.' },
            policy_snapshot: {
              target: { name: 'Review Specialist', slug: 'review-specialist' },
              review_policy: { mode: 'reviewer', required: true }
            }
          },
          result_payload: {
            review_result: {
              mode: 'reviewer',
              required: true,
              decision: 'changes_requested',
              finding_count: 2,
              blocking_finding_count: 1,
              findings: [
                {
                  title: 'Missing migration',
                  severity: 'high',
                  description: 'Add the missing migration.'
                }
              ]
            }
          }
        },
        child_run: {
          depth: 1,
          run: {
            id: 'run-child',
            status: 'waiting_user',
            input: { message: 'child task' },
            final_output_text: 'Need approval.'
          },
          invocations: []
        }
      }
    ]
  })

  assert.equal(root.run.id, 'run-parent')
  assert.equal(root.invocations[0].invocation.childRunId, 'run-child')
  assert.equal(root.invocations[0].childRun.run.status, 'waiting_user')
  assert.equal(root.invocations[0].invocation.reviewResult.decision, 'changes_requested')
  assert.equal(root.invocations[0].invocation.reviewResult.findings[0].title, 'Missing migration')
})

test('collectRunTreeNodes and collectRunTreeInvocations flatten nested structures', () => {
  const root = normalizeRunTreeNode({
    depth: 0,
    run: { id: 'run-parent', status: 'completed', input: { message: 'parent task' } },
    invocations: [
      {
        invocation: {
          id: 'invocation-1',
          parent_run_id: 'run-parent',
          child_run_id: 'run-child',
          status: 'completed',
          request_payload: {
            task: { message: 'Review the runtime contract.' },
            policy_snapshot: { target: { name: 'Review Specialist' } }
          }
        },
        child_run: {
          depth: 1,
          run: { id: 'run-child', status: 'completed', input: { message: 'child task' } },
          invocations: [
            {
              invocation: {
                id: 'invocation-2',
                parent_run_id: 'run-child',
                child_run_id: 'run-grandchild',
                status: 'completed',
                request_payload: {
                  task: { message: 'Judge the result.' },
                  policy_snapshot: { target: { name: 'Judge Specialist' } }
                }
              },
              child_run: {
                depth: 2,
                run: { id: 'run-grandchild', status: 'completed', input: { message: 'grandchild task' } },
                invocations: []
              }
            }
          ]
        }
      }
    ]
  })

  assert.deepEqual(
    collectRunTreeNodes(root).map((item) => item.run.id),
    ['run-parent', 'run-child', 'run-grandchild']
  )
  assert.deepEqual(
    collectRunTreeInvocations(root).map((item) => item.invocation.id),
    ['invocation-1', 'invocation-2']
  )
})

test('summarizeInvocationTarget and summarizeInvocationTask prefer structured handoff fields', () => {
  const invocation = {
    publicationId: 'publication-1',
    subagentDefinitionId: 'subagent-1',
    requestPayload: {
      task: {
        message: 'Review the runtime contract.'
      },
      policy_snapshot: {
        target: {
          name: 'Review Specialist',
          slug: 'review-specialist'
        }
      }
    }
  }

  assert.equal(summarizeInvocationTarget(invocation), 'Review Specialist')
  assert.equal(summarizeInvocationTask(invocation), 'Review the runtime contract.')
})

test('getInvocationReviewResult and summarizeInvocationReview normalize reviewer decisions', () => {
  const invocation = normalizeRunTreeNode({
    depth: 0,
    run: { id: 'run-parent', status: 'completed', input: { message: 'parent task' } },
    invocations: [
      {
        invocation: {
          id: 'invocation-1',
          status: 'completed',
          result_payload: {
            review_result: {
              mode: 'judge',
              required: true,
              decision: 'approved_with_findings',
              child_status: 'completed',
              finding_count: 1,
              findings: [
                {
                  title: 'Needs smoke test',
                  severity: 'medium',
                  description: 'A smoke test should run before rollout.'
                }
              ]
            }
          }
        }
      }
    ]
  }).invocations[0].invocation

  const reviewResult = getInvocationReviewResult(invocation)
  assert.equal(reviewResult.mode, 'judge')
  assert.equal(reviewDecisionLabel(reviewResult.decision), '通过但有提示')
  assert.equal(summarizeInvocationReview(invocation), 'Judge 通过但有提示 · 1 条 finding')
})

test('getInvocationQuestion and buildInvocationProtocolEntry expose waiting-user protocol details', () => {
  const item = normalizeRunTreeNode({
    depth: 0,
    run: { id: 'run-parent', status: 'completed', input: { message: 'parent task' } },
    invocations: [
      {
        invocation: {
          id: 'invocation-1',
          status: 'completed',
          child_run_id: 'run-child',
          request_payload: {
            protocol_version: 'managed-subagent.v1',
            task: {
              message: 'Review the rollout plan',
              reason: 'Need a bounded specialist verification pass.'
            },
            constraints: ['focus_paths: db/alembic/versions/example.py']
          },
          result_payload: {
            status: 'waiting_user',
            partial_result: {
              question: 'Need the migration rollout window.'
            }
          }
        },
        child_run: {
          depth: 1,
          run: {
            id: 'run-child',
            status: 'waiting_user',
            final_output_text: 'Need the migration rollout window.'
          },
          invocations: []
        }
      }
    ]
  }).invocations[0]

  assert.equal(getInvocationQuestion(item.invocation, item.childRun), 'Need the migration rollout window.')
  assert.deepEqual(buildInvocationProtocolEntry(item), {
    id: 'invocation-1',
    target: '未命名专家能力',
    status: 'waiting_user',
    protocolVersion: 'managed-subagent.v1',
    taskMessage: 'Review the rollout plan',
    delegateReason: 'Need a bounded specialist verification pass.',
    constraints: ['focus_paths: db/alembic/versions/example.py'],
    question: 'Need the migration rollout window.',
    reviewSummary: '',
    reviewResult: {
      protocolVersion: '',
      required: false,
      mode: 'none',
      approved: null,
      decision: 'not_required',
      childStatus: '',
      childRunId: '',
      summary: '',
      conclusion: '',
      findingCount: 0,
      blockingFindingCount: 0,
      blockingSeverities: [],
      findings: [],
      testGaps: [],
      explicitDecision: '',
      error: ''
    },
    childRunId: 'run-child',
    startedAt: null,
    completedAt: null
  })
})
