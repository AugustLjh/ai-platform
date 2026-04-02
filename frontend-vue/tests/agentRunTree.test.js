import test from 'node:test'
import assert from 'node:assert/strict'

import {
  collectRunTreeInvocations,
  collectRunTreeNodes,
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
