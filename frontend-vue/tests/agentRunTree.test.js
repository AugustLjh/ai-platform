import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildGovernanceRecoverySummary,
  buildInvocationProtocolEntry,
  buildPendingSubagentClarificationEntry,
  buildSubagentCollaborationSummary,
  collectResolvedSubagentInvocations,
  clarificationStateLabel,
  collectRunTreeInvocations,
  collectRunTreeNodes,
  filterRunTreeForLatestAttempt,
  filterRunTreeInvocationsForLatestAttempt,
  getInvocationClarification,
  getInvocationGovernancePolicy,
  getInvocationProgress,
  getInvocationQuestion,
  normalizeGovernancePolicy,
  progressStateLabel,
  getInvocationReviewResult,
  normalizeRunTreeNode,
  summarizeTimelineEvent,
  reviewDecisionLabel,
  summarizeGovernancePolicy,
  summarizeInvocationGovernance,
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
  assert.equal(root.invocations[0].invocation.governancePolicy.budget.usage.hasData, false)
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

test('latest attempt filters hide stale run tree branches before run.resumed', () => {
  const root = normalizeRunTreeNode({
    depth: 0,
    run: { id: 'run-parent', status: 'completed', input: { message: 'parent task' } },
    invocations: [
      {
        invocation: {
          id: 'invocation-old',
          parent_run_id: 'run-parent',
          child_run_id: 'run-old-child',
          status: 'completed',
          created_at: '2026-04-01T10:00:00.000Z',
          request_payload: { task: { message: 'Old child task' } },
          result_payload: { status: 'completed' }
        },
        child_run: {
          depth: 1,
          run: { id: 'run-old-child', status: 'completed', input: { message: 'old child task' } },
          invocations: []
        }
      },
      {
        invocation: {
          id: 'invocation-new',
          parent_run_id: 'run-parent',
          child_run_id: 'run-new-child',
          status: 'completed',
          created_at: '2026-04-01T10:02:00.000Z',
          request_payload: { task: { message: 'New child task' } },
          result_payload: { status: 'completed' }
        },
        child_run: {
          depth: 1,
          run: { id: 'run-new-child', status: 'completed', input: { message: 'new child task' } },
          invocations: []
        }
      }
    ]
  })

  const events = [
    { id: 'event-1', eventType: 'run.completed', sequence: 10, createdAt: '2026-04-01T10:00:10.000Z' },
    { id: 'event-2', eventType: 'run.resumed', sequence: 11, createdAt: '2026-04-01T10:01:00.000Z' }
  ]

  const filteredRoot = filterRunTreeForLatestAttempt(root, events)
  const filteredInvocations = filterRunTreeInvocationsForLatestAttempt(collectRunTreeInvocations(root), events)

  assert.equal(filteredRoot.invocations.length, 1)
  assert.equal(filteredRoot.invocations[0].invocation.id, 'invocation-new')
  assert.deepEqual(filteredInvocations.map((item) => item.invocation.id), ['invocation-new'])
})

test('collectResolvedSubagentInvocations normalizes async child results from run context', () => {
  const resolved = collectResolvedSubagentInvocations({
    context: {
      resolved_subagent_invocations: [
        {
          child_run_id: 'child-run-1',
          invocation_id: 'invocation-1',
          target: { slug: 'parallel-worker', name: 'Parallel Worker' },
          status: 'completed',
          step_status: 'completed',
          summary: 'Worker complete.',
          final_output_text: 'Worker complete.',
          promoted_artifacts: [
            { artifact_type: 'verification_report', name: 'async-worker-report' }
          ],
          progress: {
            protocol_version: 'managed-subagent.progress.v1',
            state: 'completed',
            summary: 'Worker complete.'
          },
          review_result: {
            decision: 'not_required',
            mode: 'none'
          },
          governance_policy: {
            protocol_version: 'managed-subagent.governance.v1',
            history: { attempt_count: 1 }
          },
          pending_completion: true
        }
      ]
    }
  })

  assert.equal(resolved.length, 1)
  assert.equal(resolved[0].target.name, 'Parallel Worker')
  assert.equal(resolved[0].promotedArtifacts[0].name, 'async-worker-report')
  assert.equal(resolved[0].progress.state, 'completed')
  assert.equal(resolved[0].reviewResult.decision, 'not_required')
  assert.equal(resolved[0].governancePolicy.history.attemptCount, 1)
  assert.equal(resolved[0].pendingCompletion, true)
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

test('review gate blocked decisions render as dangerous attention entries', () => {
  const invocation = normalizeRunTreeNode({
    depth: 0,
    run: { id: 'run-parent', status: 'running', input: { message: 'parent task' } },
    invocations: [
      {
        invocation: {
          id: 'invocation-1',
          status: 'completed',
          result_payload: {
            status: 'completed',
            review_result: {
              mode: 'reviewer',
              required: true,
              decision: 'review_gate_blocked',
              approved: false,
              gate_blocked: true,
              finding_count: 1,
              blocking_finding_count: 1,
              gate_blockers: [
                {
                  code: 'review_gate_blocked',
                  message: 'reviewer gate blocked by 1 blocking finding(s)'
                }
              ],
              recovery: {
                primary_code: 'review_gate_blocked',
                actions: ['Fix the reviewer finding before continuing.']
              }
            },
            governance_policy: {
              blockers: [
                {
                  code: 'review_gate_blocked',
                  message: 'reviewer gate blocked by 1 blocking finding(s)'
                }
              ],
              recovery: {
                primary_code: 'review_gate_blocked',
                actions: ['Fix the reviewer finding before continuing.']
              }
            }
          }
        }
      }
    ]
  }).invocations[0].invocation

  const reviewResult = getInvocationReviewResult(invocation)
  assert.equal(reviewResult.gateBlocked, true)
  assert.equal(reviewDecisionLabel(reviewResult.decision), '评审阻断')
  assert.equal(summarizeInvocationReview(invocation), 'Reviewer 评审阻断 · 已阻断 · 1 条阻塞')

  const entry = buildInvocationProtocolEntry({ invocation, childRun: null })
  assert.equal(entry.needsAttention, true)
  assert.equal(entry.attentionTone, 'danger')
  assert.equal(entry.recoverySummary, '阻塞 reviewer gate blocked by 1 blocking finding(s) · 恢复建议 Fix the reviewer finding before continuing.')
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
            progress: {
              protocol_version: 'managed-subagent.progress.v1',
              state: 'in_progress',
              summary: 'The review has started.'
            },
            task: {
              message: 'Review the rollout plan',
              reason: 'Need a bounded specialist verification pass.'
            },
            constraints: ['focus_paths: db/alembic/versions/example.py']
          },
          result_payload: {
            status: 'waiting_user',
            partial_result: {
              question: 'Need the migration rollout window.',
              progress: {
                protocol_version: 'managed-subagent.progress.v1',
                state: 'blocked',
                summary: 'Review is blocked pending rollout details.',
                completed_items: ['Checked the current rollout plan'],
                pending_items: ['Need the migration rollout window.'],
                next_action: 'Answer the clarification so the child run can continue.',
                artifact_count: 1
              },
              clarification: {
                protocol_version: 'managed-subagent.clarification.v1',
                state: 'required',
                question: 'Need the migration rollout window.',
                reason: 'The rollout plan cannot be approved without a concrete window.',
                required_fields: ['migration rollout window'],
                response_hint: 'Provide the approved rollout window and any blackout constraints.',
                blocking: true
              }
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

  assert.equal(progressStateLabel('blocked'), '阻塞中')
  assert.equal(clarificationStateLabel('required'), '待澄清')
  assert.equal(getInvocationQuestion(item.invocation, item.childRun), 'Need the migration rollout window.')
  assert.deepEqual(getInvocationProgress(item.invocation), {
    protocolVersion: 'managed-subagent.progress.v1',
    state: 'blocked',
    summary: 'Review is blocked pending rollout details.',
    completedItems: ['Checked the current rollout plan'],
    pendingItems: ['Need the migration rollout window.'],
    nextAction: 'Answer the clarification so the child run can continue.',
    artifactCount: 1,
    source: '',
    waitingUserPath: [],
    hasData: true
  })
  assert.deepEqual(getInvocationClarification(item.invocation), {
    protocolVersion: 'managed-subagent.clarification.v1',
    state: 'required',
    question: 'Need the migration rollout window.',
    reason: 'The rollout plan cannot be approved without a concrete window.',
    requiredFields: ['migration rollout window'],
    responseHint: 'Provide the approved rollout window and any blackout constraints.',
    blocking: true,
    source: '',
    waitingUserPath: [],
    hasData: true
  })
  const entry = buildInvocationProtocolEntry(item)
  assert.equal(entry.id, 'invocation-1')
  assert.equal(entry.target, '未命名专家能力')
  assert.equal(entry.status, 'waiting_user')
  assert.equal(entry.statusLabel, '等待补充')
  assert.equal(entry.protocolVersion, 'managed-subagent.v1')
  assert.equal(entry.taskMessage, 'Review the rollout plan')
  assert.equal(entry.delegateReason, 'Need a bounded specialist verification pass.')
  assert.deepEqual(entry.constraints, ['focus_paths: db/alembic/versions/example.py'])
  assert.equal(entry.question, 'Need the migration rollout window.')
  assert.equal(entry.governance.hasData, false)
  assert.deepEqual(entry.governanceBudgetLines, [])
  assert.equal(entry.reviewSummary, '')
  assert.equal(entry.reviewRequirement, '')
  assert.equal(entry.knowledgeSummary, '')
  assert.equal(entry.childRunId, 'run-child')
  assert.deepEqual(entry.waitingUserPath, [])
  assert.equal(entry.waitingUserPathSummary, '')
  assert.equal(entry.resultSummary, 'Need the migration rollout window.')
  assert.equal(
    entry.recoverySummary,
    '等待父级补充信息 · 需补充 migration rollout window · Answer the clarification so the child run can continue.'
  )
  assert.equal(
    entry.attentionSummary,
    'Need the migration rollout window. · 等待父级补充信息 · 需补充 migration rollout window · Answer the clarification so the child run can continue.'
  )
  assert.equal(entry.needsAttention, true)
  assert.equal(entry.attentionTone, 'warning')
})

test('normalizeGovernancePolicy and invocation governance summary expose runtime limits', () => {
  const invocation = normalizeRunTreeNode({
    depth: 0,
    run: { id: 'run-parent', status: 'completed', input: { message: 'parent task' } },
    invocations: [
      {
        invocation: {
          id: 'invocation-1',
          status: 'completed',
          request_payload: {
            protocol_version: 'managed-subagent.v1',
            policy_snapshot: {
              governance_policy: {
                protocol_version: 'managed-subagent.governance.v1',
                target_slug: 'review-specialist',
                limits: {
                  allow_nested_delegation: false,
                  max_delegation_depth: 1,
                  max_concurrent_delegations: 1,
                  max_retry_attempts: 2,
                  timeout_seconds: 45
                },
                budget: {
                  max_tokens: 1200,
                  max_cost_usd: 0.5
                },
                waiting_user: {
                  propagation: 'bubble_to_parent',
                  counts_as_active_child: true
                },
                enforcement: {
                  hard_limits: [
                    'max_delegation_depth',
                    'max_concurrent_delegations',
                    'max_retry_attempts',
                    'timeout_seconds'
                  ],
                  advisory_limits: ['max_tokens'],
                  note: 'Token and cost budgets are tracked from observed child usage and remain advisory while provider accounting may still be incomplete.'
                }
              }
            }
          },
          result_payload: {
            governance_policy: {
              protocol_version: 'managed-subagent.governance.v1',
              budget: {
                usage: {
                  total_tokens: 640,
                  cost_usd: 0.18,
                  source: 'metadata.governance_usage'
                },
                prior_usage: {
                  total_tokens: 320,
                  cost_usd: 0.07,
                  source: 'step_history'
                },
                last_invocation_usage: {
                  total_tokens: 320,
                  cost_usd: 0.11,
                  source: 'metadata.governance_usage'
                },
                remaining_tokens: 560,
                usage_status: 'within_limits'
              },
              history: {
                target_slug: 'review-specialist',
                attempt_count: 2,
                failed_attempt_count: 1,
                active_child_count: 0,
                waiting_user_count: 1,
                bubble_to_parent_count: 1,
                continue_parent_count: 0,
                child_only_count: 0
              },
              warnings: ['budget limits are attached to the invocation as advisory governance metadata']
            }
          }
        }
      }
    ]
  }).invocations[0].invocation

  const governance = getInvocationGovernancePolicy(invocation)
  assert.deepEqual(normalizeGovernancePolicy({
    protocol_version: 'managed-subagent.governance.v1',
    limits: { timeout_seconds: 30 }
  }), {
    protocolVersion: 'managed-subagent.governance.v1',
    targetSlug: '',
    limits: {
      allowNestedDelegation: null,
      maxDelegationDepth: null,
      maxParentDelegations: null,
      maxConcurrentDelegations: null,
      maxRetryAttempts: null,
      timeoutSeconds: 30,
      maxContextObservations: null
    },
    budget: {
      maxTokens: null,
      maxCostUsd: null,
      remainingTokens: null,
      remainingCostUsd: null,
      usageStatus: '',
      usage: {
        promptTokens: null,
        completionTokens: null,
        totalTokens: null,
        costUsd: null,
        source: '',
        hasData: false
      },
      priorUsage: {
        promptTokens: null,
        completionTokens: null,
        totalTokens: null,
        costUsd: null,
        source: '',
        hasData: false
      },
      lastInvocationUsage: {
        promptTokens: null,
        completionTokens: null,
        totalTokens: null,
        costUsd: null,
        source: '',
        hasData: false
      },
      raw: {}
    },
    waitingUserPropagation: '',
    waitingUserCountsAsActiveChild: null,
    enforcement: {
      hardLimits: [],
      advisoryLimits: [],
      note: ''
    },
    blockers: [],
    recovery: {
      recoverable: false,
      primaryCode: '',
      summary: '',
      actions: []
    },
    warnings: [],
    history: {
      targetSlug: '',
      attemptCount: 0,
      failedAttemptCount: 0,
      activeChildCount: 0,
      waitingUserCount: 0,
      bubbleToParentCount: 0,
      continueParentCount: 0,
      childOnlyCount: 0,
      statuses: [],
      waitingUserStrategies: []
    },
    raw: {
      protocol_version: 'managed-subagent.governance.v1',
      limits: { timeout_seconds: 30 }
    },
    hasData: true
  })
  assert.equal(governance.protocolVersion, 'managed-subagent.governance.v1')
  assert.equal(governance.limits.allowNestedDelegation, false)
  assert.equal(governance.limits.maxDelegationDepth, 1)
  assert.equal(governance.limits.maxRetryAttempts, 2)
  assert.equal(governance.limits.timeoutSeconds, 45)
  assert.equal(governance.budget.maxTokens, 1200)
  assert.equal(governance.budget.maxCostUsd, 0.5)
  assert.equal(governance.budget.usage.totalTokens, 640)
  assert.equal(governance.budget.usage.costUsd, 0.18)
  assert.equal(governance.budget.priorUsage.totalTokens, 320)
  assert.equal(governance.budget.lastInvocationUsage.totalTokens, 320)
  assert.equal(governance.budget.usageStatus, 'within_limits')
  assert.equal(governance.waitingUserPropagation, 'bubble_to_parent')
  assert.equal(governance.history.attemptCount, 2)
  assert.equal(governance.history.waitingUserCount, 1)
  assert.equal(governance.warnings[0], 'budget limits are attached to the invocation as advisory governance metadata')
  assert.equal(summarizeGovernancePolicy(governance), 'timeout 45s · retry 2 · 并发 1 · 深度 1 · tokens 640/1200 · cost $0.18/$0.5 · 等待用户 1 · 上浮 1')
  assert.equal(summarizeInvocationGovernance(invocation), 'timeout 45s · retry 2 · 并发 1 · 深度 1 · tokens 640/1200 · cost $0.18/$0.5 · 等待用户 1 · 上浮 1')

  const entry = buildInvocationProtocolEntry({ invocation, childRun: null })
  assert.equal(entry.governance.protocolVersion, 'managed-subagent.governance.v1')
  assert.equal(entry.governanceSummary, 'timeout 45s · retry 2 · 并发 1 · 深度 1 · tokens 640/1200 · cost $0.18/$0.5 · 等待用户 1 · 上浮 1')
  assert.deepEqual(entry.governance.enforcement.hardLimits, [
    'max_delegation_depth',
    'max_concurrent_delegations',
    'max_retry_attempts',
    'timeout_seconds'
  ])
})

test('normalizeGovernancePolicy and recovery summary expose structured blockers', () => {
  const governance = normalizeGovernancePolicy({
    blockers: [
      {
        code: 'concurrency_limit_exceeded',
        message: '1 unresolved child run already exists.',
        recovery_actions: [
          'Wait for the existing child run to finish.',
          'Increase max_concurrent_delegations only if the tasks are independent.'
        ]
      }
    ],
    recovery: {
      recoverable: true,
      primary_code: 'concurrency_limit_exceeded',
      summary: 'Wait for the current child run or raise the concurrency limit.',
      actions: [
        'Wait for the existing child run to finish.',
        'Increase max_concurrent_delegations only if the tasks are independent.'
      ]
    }
  })

  assert.equal(governance.hasData, true)
  assert.equal(governance.blockers[0].code, 'concurrency_limit_exceeded')
  assert.equal(governance.recovery.primaryCode, 'concurrency_limit_exceeded')
  assert.equal(
    buildGovernanceRecoverySummary(governance),
    'Wait for the existing child run to finish. · Increase max_concurrent_delegations only if the tasks are independent.'
  )
})

test('buildPendingSubagentClarificationEntry and protocol entry preserve multihop waiting-user and budget context', () => {
  const run = {
    status: 'waiting_user',
    finalOutputText: 'Need final production rollout window.',
    context: {
      pending_subagent_clarification: {
        child_run_id: 'child-run-1',
        question: 'Need final production rollout window.',
        target: {
          slug: 'review-specialist',
          name: 'Review Specialist'
        },
        progress: {
          protocol_version: 'managed-subagent.progress.v1',
          state: 'blocked',
          summary: 'Nested review is blocked on deployment timing.',
          waiting_user_path: [
            { run_id: 'run-parent', role: 'parent', status: 'running' },
            { run_id: 'child-run-1', role: 'parent', status: 'running' },
            { run_id: 'grandchild-run-1', role: 'child', status: 'waiting_user' }
          ]
        },
        clarification: {
          protocol_version: 'managed-subagent.clarification.v1',
          state: 'required',
          question: 'Need final production rollout window.',
          required_fields: ['production rollout window'],
          response_hint: 'Provide the approved production rollout window.'
        },
        governance_policy: {
          protocol_version: 'managed-subagent.governance.v1',
          target_slug: 'review-specialist',
          waiting_user: {
            propagation: 'bubble_to_parent'
          },
          budget: {
            usage: {
              total_tokens: 660,
              cost_usd: 0.23
            },
            prior_usage: {
              total_tokens: 440,
              cost_usd: 0.12
            },
            last_invocation_usage: {
              total_tokens: 220,
              cost_usd: 0.11
            },
            usage_status: 'within_limits'
          }
        },
        waiting_user_path: [
          { run_id: 'run-parent', role: 'parent', status: 'running' },
          { run_id: 'child-run-1', role: 'parent', status: 'running' },
          { run_id: 'grandchild-run-1', role: 'child', status: 'waiting_user' }
        ]
      }
    }
  }

  const clarificationEntry = buildPendingSubagentClarificationEntry(run)
  assert.equal(clarificationEntry.targetName, 'Review Specialist')
  assert.equal(clarificationEntry.waitingUserPath.length, 3)
  assert.equal(clarificationEntry.waitingUserPathSummary, '父:运行 -> 父:运行 -> 子:等待补充')
  assert.deepEqual(clarificationEntry.governanceBudgetLines, [
    'tokens 660',
    'cost $0.23',
    '历史累计 440 tokens · $0.12',
    '本次 child 220 tokens · $0.11',
    '预算状态 within_limits'
  ])

  const timelineSummary = summarizeTimelineEvent({
    eventType: 'subagent.waiting_user',
    payload: {
      child_status: 'waiting_user',
      child_run_id: 'child-run-1',
      handoff_envelope: {
        protocol_version: 'managed-subagent.v1',
        task: { message: 'Review the rollout plan' },
        policy_snapshot: {
          target: { name: 'Review Specialist', slug: 'review-specialist' }
        }
      },
      progress: {
        protocol_version: 'managed-subagent.progress.v1',
        state: 'blocked',
        summary: 'Nested review is blocked on deployment timing.'
      },
      clarification: {
        protocol_version: 'managed-subagent.clarification.v1',
        state: 'required',
        question: 'Need final production rollout window.'
      },
      governance_policy: {
        protocol_version: 'managed-subagent.governance.v1',
        waiting_user: { propagation: 'bubble_to_parent' },
        budget: {
          usage: { total_tokens: 660, cost_usd: 0.23 }
        }
      }
    }
  })
  assert.match(timelineSummary, /Review Specialist/)
  assert.match(timelineSummary, /等待补充/)
  assert.match(timelineSummary, /治理 已用 660 tokens · 已用 \$0.23/)
  assert.match(timelineSummary, /Need final production rollout window\./)
})

test('buildSubagentCollaborationSummary aggregates timeline, artifacts, and reviewer blocks', () => {
  const root = normalizeRunTreeNode({
    depth: 0,
    run: { id: 'run-parent', status: 'running', input: { message: 'parent task' } },
    invocations: [
      {
        invocation: {
          id: 'invocation-review',
          status: 'completed',
          child_run_id: 'child-review',
          request_payload: {
            task: { message: 'Review the worker patch.' },
            policy_snapshot: { target: { name: 'Reviewer' } }
          },
          result_payload: {
            status: 'completed',
            final_result: {
              artifacts: [
                {
                  artifact_type: 'review_findings',
                  name: 'Review Findings',
                  payload: {
                    items: [
                      { title: 'Unsafe writeback', severity: 'high', path: 'src/app.py' }
                    ]
                  }
                }
              ]
            },
            review_result: {
              mode: 'reviewer',
              required: true,
              decision: 'review_gate_blocked',
              gate_blocked: true,
              finding_count: 1,
              blocking_finding_count: 1,
              summary: 'Unsafe writeback must be fixed.',
              recovery: {
                actions: ['Fix the blocking finding before continuing.']
              }
            }
          }
        },
        child_run: {
          depth: 1,
          run: { id: 'child-review', status: 'completed', input: { message: 'review' } },
          invocations: []
        }
      }
    ]
  })

  const resolved = collectResolvedSubagentInvocations({
    context: {
      resolved_subagent_invocations: [
        {
          child_run_id: 'child-worker',
          invocation_id: 'invocation-worker',
          target: { name: 'Worker', slug: 'worker' },
          status: 'completed',
          summary: 'Patch ready.',
          promoted_artifacts: [
            { artifact_type: 'code_patch', name: 'Worker Patch', payload: { diff: '+new' } }
          ],
          review_result: { decision: 'not_required', mode: 'none' }
        }
      ]
    }
  })

  const summary = buildSubagentCollaborationSummary({
    runTreeInvocations: collectRunTreeInvocations(root),
    resolvedInvocations: resolved,
    artifacts: [
      { artifactType: 'verification_report', name: 'npm test', payload: { status: 'completed' } }
    ],
    events: [
      {
        id: 'event-1',
        sequence: 1,
        eventType: 'subagent.completed',
        payload: {
          child_status: 'completed',
          child_run_id: 'child-worker',
          handoff_envelope: {
            task: { message: 'Implement patch' },
            policy_snapshot: { target: { name: 'Worker' } }
          }
        },
        createdAt: '2026-05-17T00:00:00+00:00'
      }
    ]
  })

  assert.equal(summary.totalInvocations, 2)
  assert.equal(summary.completedCount, 2)
  assert.equal(summary.reviewBlockCount, 1)
  assert.equal(summary.promotedArtifactCount, 2)
  assert.equal(summary.directArtifactCount, 1)
  assert.equal(summary.artifactTypeCounts['审查发现'], 1)
  assert.equal(summary.artifactTypeCounts.Patch, 1)
  assert.equal(summary.artifactTypeCounts['验证报告'], 1)
  assert.equal(summary.reviewBlocks[0].target, 'Reviewer')
  assert.equal(summary.reviewBlocks[0].recoveryActions[0], 'Fix the blocking finding before continuing.')
  assert.equal(summary.eventTimeline.length, 1)
})

test('buildSubagentCollaborationSummary keeps only latest attempt data after resume', () => {
  const root = normalizeRunTreeNode({
    depth: 0,
    run: { id: 'run-parent', status: 'running', input: { message: 'parent task' } },
    invocations: [
      {
        invocation: {
          id: 'invocation-old',
          parent_run_id: 'run-parent',
          child_run_id: 'child-old',
          status: 'completed',
          created_at: '2026-04-01T10:00:00.000Z',
          request_payload: {
            task: { message: 'Old attempt' },
            policy_snapshot: { target: { name: 'Old Worker' } }
          },
          result_payload: {
            status: 'completed',
            final_result: {
              artifacts: [
                {
                  artifact_type: 'code_patch',
                  name: 'Old Patch',
                  payload: { operation: 'modify', diff: '+old' }
                }
              ]
            }
          }
        },
        child_run: {
          depth: 1,
          run: { id: 'child-old', status: 'completed', input: { message: 'old attempt' } },
          invocations: []
        }
      },
      {
        invocation: {
          id: 'invocation-new',
          parent_run_id: 'run-parent',
          child_run_id: 'child-new',
          status: 'completed',
          created_at: '2026-04-01T10:02:00.000Z',
          request_payload: {
            task: { message: 'New attempt' },
            policy_snapshot: { target: { name: 'New Worker' } }
          },
          result_payload: {
            status: 'completed',
            final_result: {
              artifacts: [
                {
                  artifact_type: 'verification_report',
                  name: 'New Report',
                  payload: { status: 'completed' }
                }
              ]
            }
          }
        },
        child_run: {
          depth: 1,
          run: { id: 'child-new', status: 'completed', input: { message: 'new attempt' } },
          invocations: []
        }
      }
    ]
  })

  const summary = buildSubagentCollaborationSummary({
    runTreeInvocations: collectRunTreeInvocations(root),
    resolvedInvocations: [],
    artifacts: [
      { artifactType: 'verification_report', name: 'Current Report', payload: { status: 'completed' } }
    ],
    events: [
      { id: 'event-1', eventType: 'run.completed', sequence: 10, createdAt: '2026-04-01T10:00:10.000Z' },
      { id: 'event-2', eventType: 'run.resumed', sequence: 11, createdAt: '2026-04-01T10:01:00.000Z' },
      {
        id: 'event-3',
        eventType: 'subagent.completed',
        sequence: 12,
        createdAt: '2026-04-01T10:02:30.000Z',
        payload: {
          child_status: 'completed',
          child_run_id: 'child-new',
          handoff_envelope: {
            task: { message: 'New attempt' },
            policy_snapshot: { target: { name: 'New Worker' } }
          }
        }
      }
    ]
  })

  assert.equal(summary.totalInvocations, 1)
  assert.equal(summary.promotedArtifactCount, 1)
  assert.equal(summary.directArtifactCount, 1)
  assert.equal(summary.eventTimeline.length, 1)
  assert.equal(summary.timeline[0].target, 'New Worker')
  assert.equal(summary.promotedArtifacts[0].sourceChildRunId, 'child-new')
})
