import test from "node:test";
import assert from "node:assert/strict";

import {
  bridgeRemovalStatusLabel,
  compatibilityDetailLabel,
  normalizeBridgeRemovalReadiness,
  normalizeMetadataAliasFreezePreview,
  normalizeSubagentGovernance,
  normalizeSubagentPublicationEvent,
  normalizeSubagentTenantGovernanceSummary,
  normalizeSubagentPublicationPreview,
  publicationEventStageLabel,
  publicationChangeLabel,
  publicationRiskLabel,
} from "../src/utils/subagentGovernance.js";

test("normalizeSubagentPublicationPreview keeps risk, counts and affected agents", () => {
  const preview = normalizeSubagentPublicationPreview({
    change_type: "rollback",
    risk_level: "high",
    requires_confirmation: true,
    summary: "即将把 publication 从 v3 回滚到 v2。",
    confirmation_message: "这是高风险操作。",
    current: {
      version_id: "version-3",
      version_number: 3,
      status: "active",
      publication_scope: "tenant",
    },
    target: {
      version_id: "version-2",
      version_number: 2,
      status: "active",
      publication_scope: "tenant",
    },
    impacted_authorization_count: 3,
    enabled_authorization_count: 2,
    inactive_authorization_count: 1,
    compatibility_mode: true,
    recommended_actions: ["先创建测试运行"],
    affected_agents: [
      {
        authorization_id: "auth-1",
        agent_definition_id: "agent-1",
        agent_name: "Planner",
        agent_status: "active",
        authorization_status: "enabled",
      },
    ],
  });

  assert.equal(preview.changeType, "rollback");
  assert.equal(preview.riskLevel, "high");
  assert.equal(preview.requiresConfirmation, true);
  assert.equal(preview.current.versionNumber, 3);
  assert.equal(preview.target.versionId, "version-2");
  assert.equal(preview.enabledAuthorizationCount, 2);
  assert.equal(preview.compatibilityMode, true);
  assert.equal(preview.affectedAgents[0].agentName, "Planner");
});

test("publication labels map to expected chinese copy", () => {
  assert.equal(publicationChangeLabel("rollout"), "发布切换");
  assert.equal(publicationChangeLabel("rollback"), "版本回滚");
  assert.equal(publicationRiskLabel("medium"), "中风险");
  assert.equal(publicationRiskLabel("high"), "高风险");
});

test("normalizeSubagentGovernance keeps compatibility details and readiness", () => {
  const governance = normalizeSubagentGovernance({
    compatibility_mode: true,
    host_agent_definition_id: "host-1",
    compatibility_details: [
      {
        kind: "metadata_alias",
        summary: "definition metadata 里仍残留 legacy host alias。",
        reference_key: "target_agent_definition_id/agent_definition_id",
        impacted_agent_count: 1,
        active_agent_count: 1,
        agents: [
          {
            agent_definition_id: "agent-1",
            agent_name: "Planner",
            agent_status: "active",
          },
        ],
      },
    ],
    latest_version_number: 4,
    published_version_number: 3,
    is_published_version_latest: false,
    authorization_count: 3,
    enabled_authorization_count: 2,
    inactive_authorization_count: 1,
    rollback_candidate_count: 2,
    has_rollback_candidate: true,
    warnings: [
      {
        code: "legacy-bindings-present",
        severity: "warning",
        message: "仍有旧 binding。",
      },
    ],
  });

  assert.equal(governance.compatibilityMode, true);
  assert.equal(governance.compatibilityDetails[0].kind, "metadata_alias");
  assert.equal(
    governance.compatibilityDetails[0].agents[0].agentName,
    "Planner",
  );
  assert.equal(governance.rollbackCandidateCount, 2);
  assert.equal(governance.warnings[0].code, "legacy-bindings-present");
  assert.equal(compatibilityDetailLabel("metadata_alias"), "遗留元数据别名");
});

test("normalizeBridgeRemovalReadiness keeps blocking counters and checklist", () => {
  const readiness = normalizeBridgeRemovalReadiness({
    status: "blocked",
    ready: false,
    blocking_issue_count: 2,
    pending_issue_count: 1,
    summary: "仍有删桥后收口阻塞项。",
    recommended_actions: ["先执行 metadata alias freeze"],
    checklist: [
      {
        key: "metadata_aliases",
        label: "Metadata alias 冻结",
        status: "blocked",
        blocking: true,
        summary: "仍有旧 alias。",
      },
    ],
  });

  assert.equal(readiness.status, "blocked");
  assert.equal(readiness.blockingIssueCount, 2);
  assert.equal(readiness.checklist[0].label, "Metadata alias 冻结");
  assert.equal(bridgeRemovalStatusLabel("ready"), "可删桥接");
});

test("normalizeMetadataAliasFreezePreview keeps counts and capability candidates", () => {
  const preview = normalizeMetadataAliasFreezePreview({
    executable: true,
    requires_confirmation: true,
    summary: "tenant 内有 2 个 capability 仍残留 legacy metadata alias。",
    confirmation_message: "会直接改写 metadata，但不会创建新版本。",
    scope: "tenant",
    definition_ids: ["subagent-1", "subagent-2"],
    impacted_capability_count: 2,
    authorization_count: 5,
    enabled_authorization_count: 3,
    inactive_authorization_count: 2,
    recommended_actions: ["执行后重新检查 compatibility detail"],
    affected_capabilities: [
      {
        definition_id: "subagent-1",
        definition_name: "Code Reviewer",
        host_agent_definition_id: "agent-1",
        legacy_alias_key: "target_agent_definition_id",
        legacy_alias_value: "agent-1",
        authorization_count: 3,
        enabled_authorization_count: 2,
        inactive_authorization_count: 1,
      },
    ],
  });

  assert.equal(preview.executable, true);
  assert.equal(preview.scope, "tenant");
  assert.equal(preview.definitionIds.length, 2);
  assert.equal(preview.impactedCapabilityCount, 2);
  assert.equal(preview.affectedCapabilities[0].definitionName, "Code Reviewer");
  assert.equal(preview.affectedCapabilities[0].legacyAliasKey, "target_agent_definition_id");
});

test("normalizeSubagentGovernance keeps metadata alias freeze preview", () => {
  const governance = normalizeSubagentGovernance({
    compatibility_mode: true,
    can_freeze_metadata_aliases: true,
    metadata_alias_freeze_preview: {
      executable: true,
      scope: "selection",
      impacted_capability_count: 1,
      affected_capabilities: [
        {
          definition_id: "subagent-1",
          definition_name: "Code Reviewer",
        },
      ],
    },
  });

  assert.equal(governance.canFreezeMetadataAliases, true);
  assert.equal(governance.metadataAliasFreezePreview.scope, "selection");
  assert.equal(governance.metadataAliasFreezePreview.impactedCapabilityCount, 1);
  assert.equal(
    governance.metadataAliasFreezePreview.affectedCapabilities[0].definitionId,
    "subagent-1",
  );
});

test("normalizeSubagentPublicationEvent keeps governance notes and actor info", () => {
  const event = normalizeSubagentPublicationEvent({
    id: "event-1",
    subagent_definition_name: "Code Reviewer",
    subagent_definition_status: "active",
    event_stage: "executed",
    action_type: "rollback",
    change_type: "rollback",
    risk_level: "high",
    requires_confirmation: true,
    confirmed: true,
    version_id: "version-2",
    version_number: 2,
    previous_version_id: "version-3",
    previous_version_number: 3,
    impacted_authorization_count: 4,
    enabled_authorization_count: 3,
    inactive_authorization_count: 1,
    compatibility_mode: true,
    summary: "即将把 publication 从 v3 回滚到 v2。",
    change_reason: "线上回归需要止血。",
    change_notes: "已通知值班同学观察。",
    rollback_recovery_plan: "修复完成后重新发布 v3.1。",
    recommended_actions: ["先创建测试运行"],
    affected_agents: [
      {
        authorization_id: "auth-1",
        agent_definition_id: "agent-1",
        agent_name: "Planner",
        agent_status: "active",
        authorization_status: "enabled",
      },
    ],
    actor_user_id: "user-1",
    actor_user_email: "ops@example.com",
    created_at: "2026-04-15T12:00:00Z",
  });

  assert.equal(event.eventStage, "executed");
  assert.equal(event.definitionName, "Code Reviewer");
  assert.equal(event.definitionStatus, "active");
  assert.equal(event.changeReason, "线上回归需要止血。");
  assert.equal(event.rollbackRecoveryPlan, "修复完成后重新发布 v3.1。");
  assert.equal(event.actorUserEmail, "ops@example.com");
  assert.equal(event.affectedAgents[0].agentName, "Planner");
  assert.equal(publicationEventStageLabel("previewed"), "预演");
});

test("normalizeSubagentTenantGovernanceSummary keeps counts and filters", () => {
  const summary = normalizeSubagentTenantGovernanceSummary({
    total_capabilities: 8,
    compatibility_capabilities: 3,
    host_override_capabilities: 1,
    metadata_alias_capabilities: 2,
    publication_missing_count: 1,
    publication_not_latest_count: 4,
    authorization_count: 10,
    enabled_authorization_count: 7,
    inactive_authorization_count: 3,
    high_risk_event_count: 2,
    confirmation_required_event_count: 4,
    compatibility_event_count: 5,
    recent_event_count: 9,
    action_type_counts: { rollout: 3 },
    change_type_counts: { rollback: 2 },
    event_stage_counts: { executed: 6 },
    risk_level_counts: { high: 2 },
    event_filters: {
      definition_id: "subagent-1",
      action_type: "rollback",
      event_stage: "executed",
      risk_level: "high",
      compatibility_mode: "true",
      limit: 10,
      offset: 20,
    },
  });

  assert.equal(summary.totalCapabilities, 8);
  assert.equal(summary.compatibilityCapabilities, 3);
  assert.equal(summary.actionTypeCounts.rollout, 3);
  assert.equal(summary.filters.definitionId, "subagent-1");
  assert.equal(summary.filters.compatibilityMode, "true");
  assert.equal(summary.filters.offset, 20);
});
