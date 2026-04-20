export const normalizePublicationEndpoint = (raw = null) => {
  if (!raw || typeof raw !== "object") return null;
  return {
    versionId: raw.version_id || raw.versionId || "",
    versionNumber: Number(raw.version_number || raw.versionNumber || 0),
    status: raw.status || "",
    publicationScope: raw.publication_scope || raw.publicationScope || "",
    publicationTenantId:
      raw.publication_tenant_id || raw.publicationTenantId || "",
  };
};

export const normalizePublicationImpactAgent = (raw = {}) => ({
  authorizationId: raw.authorization_id || raw.authorizationId || "",
  agentDefinitionId: raw.agent_definition_id || raw.agentDefinitionId || "",
  agentName: raw.agent_name || raw.agentName || "",
  agentStatus: raw.agent_status || raw.agentStatus || "",
  authorizationStatus:
    raw.authorization_status || raw.authorizationStatus || "",
});

export const normalizeSubagentCompatibilityDetail = (raw = null) => {
  if (!raw || typeof raw !== "object") return null;
  return {
    kind: raw.kind || "",
    summary: raw.summary || "",
    hostAgentDefinitionId:
      raw.host_agent_definition_id || raw.hostAgentDefinitionId || "",
    referenceKey: raw.reference_key || raw.referenceKey || "",
    impactedAgentCount: Number(
      raw.impacted_agent_count || raw.impactedAgentCount || 0,
    ),
    activeAgentCount: Number(
      raw.active_agent_count || raw.activeAgentCount || 0,
    ),
    agents: Array.isArray(raw.agents)
      ? raw.agents.map(normalizePublicationImpactAgent)
      : [],
  };
};

export const normalizeBridgeRemovalChecklistItem = (raw = null) => {
  if (!raw || typeof raw !== "object") return null;
  return {
    key: raw.key || "",
    label: raw.label || "",
    status: raw.status || "pending",
    blocking: Boolean(raw.blocking),
    summary: raw.summary || "",
    recommendedActions: Array.isArray(
      raw.recommended_actions || raw.recommendedActions,
    )
      ? [...(raw.recommended_actions || raw.recommendedActions)].filter(Boolean)
      : [],
  };
};

export const normalizeBridgeRemovalReadiness = (raw = null) => {
  if (!raw || typeof raw !== "object") return null;
  return {
    status: raw.status || "pending",
    ready: Boolean(raw.ready),
    blockingIssueCount: Number(
      raw.blocking_issue_count || raw.blockingIssueCount || 0,
    ),
    pendingIssueCount: Number(
      raw.pending_issue_count || raw.pendingIssueCount || 0,
    ),
    summary: raw.summary || "",
    recommendedActions: Array.isArray(
      raw.recommended_actions || raw.recommendedActions,
    )
      ? [...(raw.recommended_actions || raw.recommendedActions)].filter(Boolean)
      : [],
    checklist: Array.isArray(raw.checklist)
      ? raw.checklist.map(normalizeBridgeRemovalChecklistItem).filter(Boolean)
      : [],
  };
};

export const normalizeSubagentGovernance = (raw = null) => {
  if (!raw || typeof raw !== "object") return null;
  return {
    compatibilityMode: Boolean(raw.compatibility_mode || raw.compatibilityMode),
    hostAgentDefinitionId:
      raw.host_agent_definition_id || raw.hostAgentDefinitionId || "",
    canFreezeMetadataAliases: Boolean(
      raw.can_freeze_metadata_aliases || raw.canFreezeMetadataAliases,
    ),
    compatibilityDetails: Array.isArray(
      raw.compatibility_details || raw.compatibilityDetails,
    )
      ? (raw.compatibility_details || raw.compatibilityDetails)
          .map(normalizeSubagentCompatibilityDetail)
          .filter(Boolean)
      : [],
    latestVersionNumber: Number(
      raw.latest_version_number || raw.latestVersionNumber || 0,
    ),
    publishedVersionNumber: Number(
      raw.published_version_number || raw.publishedVersionNumber || 0,
    ),
    isPublishedVersionLatest: Boolean(
      raw.is_published_version_latest || raw.isPublishedVersionLatest,
    ),
    authorizationCount: Number(
      raw.authorization_count || raw.authorizationCount || 0,
    ),
    enabledAuthorizationCount: Number(
      raw.enabled_authorization_count || raw.enabledAuthorizationCount || 0,
    ),
    inactiveAuthorizationCount: Number(
      raw.inactive_authorization_count || raw.inactiveAuthorizationCount || 0,
    ),
    rollbackCandidateCount: Number(
      raw.rollback_candidate_count || raw.rollbackCandidateCount || 0,
    ),
    hasRollbackCandidate: Boolean(
      raw.has_rollback_candidate || raw.hasRollbackCandidate,
    ),
    nextPublicationPreview: normalizeSubagentPublicationPreview(
      raw.next_publication_preview || raw.nextPublicationPreview,
    ),
    metadataAliasFreezePreview: normalizeMetadataAliasFreezePreview(
      raw.metadata_alias_freeze_preview || raw.metadataAliasFreezePreview,
    ),
    bridgeRemovalReadiness: normalizeBridgeRemovalReadiness(
      raw.bridge_removal_readiness || raw.bridgeRemovalReadiness,
    ),
    warnings: Array.isArray(raw.warnings)
      ? raw.warnings.map((item) => ({
          code: item.code || "",
          severity: item.severity || "info",
          message: item.message || "",
        }))
      : [],
  };
};

export const normalizeMetadataAliasFreezeCandidate = (raw = null) => {
  if (!raw || typeof raw !== "object") return null;
  return {
    definitionId: raw.definition_id || raw.definitionId || "",
    definitionName: raw.definition_name || raw.definitionName || "",
    definitionStatus: raw.definition_status || raw.definitionStatus || "",
    hostAgentDefinitionId:
      raw.host_agent_definition_id || raw.hostAgentDefinitionId || "",
    legacyAliasKey: raw.legacy_alias_key || raw.legacyAliasKey || "",
    legacyAliasValue: raw.legacy_alias_value || raw.legacyAliasValue || "",
    authorizationCount: Number(
      raw.authorization_count || raw.authorizationCount || 0,
    ),
    enabledAuthorizationCount: Number(
      raw.enabled_authorization_count || raw.enabledAuthorizationCount || 0,
    ),
    inactiveAuthorizationCount: Number(
      raw.inactive_authorization_count || raw.inactiveAuthorizationCount || 0,
    ),
  };
};

export const normalizeMetadataAliasFreezePreview = (raw = null) => {
  if (!raw || typeof raw !== "object") return null;
  return {
    executable: Boolean(raw.executable),
    requiresConfirmation: Boolean(
      raw.requires_confirmation || raw.requiresConfirmation,
    ),
    summary: raw.summary || "",
    confirmationMessage:
      raw.confirmation_message || raw.confirmationMessage || "",
    blockedReason: raw.blocked_reason || raw.blockedReason || "",
    scope: raw.scope || "tenant",
    definitionIds: Array.isArray(raw.definition_ids || raw.definitionIds)
      ? [...(raw.definition_ids || raw.definitionIds)].filter(Boolean)
      : [],
    impactedCapabilityCount: Number(
      raw.impacted_capability_count || raw.impactedCapabilityCount || 0,
    ),
    authorizationCount: Number(
      raw.authorization_count || raw.authorizationCount || 0,
    ),
    enabledAuthorizationCount: Number(
      raw.enabled_authorization_count || raw.enabledAuthorizationCount || 0,
    ),
    inactiveAuthorizationCount: Number(
      raw.inactive_authorization_count || raw.inactiveAuthorizationCount || 0,
    ),
    recommendedActions: Array.isArray(
      raw.recommended_actions || raw.recommendedActions,
    )
      ? [...(raw.recommended_actions || raw.recommendedActions)].filter(Boolean)
      : [],
    affectedCapabilities: Array.isArray(
      raw.affected_capabilities || raw.affectedCapabilities,
    )
      ? (raw.affected_capabilities || raw.affectedCapabilities)
          .map(normalizeMetadataAliasFreezeCandidate)
          .filter(Boolean)
      : [],
  };
};

export const normalizeSubagentPublicationPreview = (raw = null) => {
  if (!raw || typeof raw !== "object") return null;
  return {
    changeType: raw.change_type || raw.changeType || "metadata_update",
    riskLevel: raw.risk_level || raw.riskLevel || "low",
    requiresConfirmation: Boolean(
      raw.requires_confirmation || raw.requiresConfirmation,
    ),
    summary: raw.summary || "",
    confirmationMessage:
      raw.confirmation_message || raw.confirmationMessage || "",
    current: normalizePublicationEndpoint(raw.current),
    target: normalizePublicationEndpoint(raw.target),
    impactedAuthorizationCount: Number(
      raw.impacted_authorization_count || raw.impactedAuthorizationCount || 0,
    ),
    enabledAuthorizationCount: Number(
      raw.enabled_authorization_count || raw.enabledAuthorizationCount || 0,
    ),
    inactiveAuthorizationCount: Number(
      raw.inactive_authorization_count || raw.inactiveAuthorizationCount || 0,
    ),
    compatibilityMode: Boolean(raw.compatibility_mode || raw.compatibilityMode),
    recommendedActions: Array.isArray(
      raw.recommended_actions || raw.recommendedActions,
    )
      ? [...(raw.recommended_actions || raw.recommendedActions)].filter(Boolean)
      : [],
    affectedAgents: Array.isArray(raw.affected_agents || raw.affectedAgents)
      ? (raw.affected_agents || raw.affectedAgents).map(
          normalizePublicationImpactAgent,
        )
      : [],
  };
};

export const normalizeSubagentPublicationEvent = (raw = null) => {
  if (!raw || typeof raw !== "object") return null;
  const recommendedActions = raw.recommended_actions || raw.recommendedActions;
  const affectedAgents = raw.affected_agents || raw.affectedAgents;
  return {
    id: raw.id || "",
    tenantId: raw.tenant_id || raw.tenantId || "",
    definitionId: raw.subagent_definition_id || raw.subagentDefinitionId || "",
    definitionName:
      raw.subagent_definition_name || raw.subagentDefinitionName || "",
    definitionStatus:
      raw.subagent_definition_status || raw.subagentDefinitionStatus || "",
    publicationId: raw.publication_id || raw.publicationId || "",
    eventStage: raw.event_stage || raw.eventStage || "executed",
    actionType: raw.action_type || raw.actionType || "",
    changeType: raw.change_type || raw.changeType || "",
    riskLevel: raw.risk_level || raw.riskLevel || "low",
    requiresConfirmation: Boolean(
      raw.requires_confirmation || raw.requiresConfirmation,
    ),
    confirmed: Boolean(raw.confirmed),
    versionId: raw.version_id || raw.versionId || "",
    versionNumber: Number(raw.version_number || raw.versionNumber || 0),
    previousVersionId: raw.previous_version_id || raw.previousVersionId || "",
    previousVersionNumber: Number(
      raw.previous_version_number || raw.previousVersionNumber || 0,
    ),
    publicationScope: raw.publication_scope || raw.publicationScope || "tenant",
    previousPublicationScope:
      raw.previous_publication_scope ||
      raw.previousPublicationScope ||
      "tenant",
    status: raw.status || "active",
    previousStatus: raw.previous_status || raw.previousStatus || "active",
    impactedAuthorizationCount: Number(
      raw.impacted_authorization_count || raw.impactedAuthorizationCount || 0,
    ),
    enabledAuthorizationCount: Number(
      raw.enabled_authorization_count || raw.enabledAuthorizationCount || 0,
    ),
    inactiveAuthorizationCount: Number(
      raw.inactive_authorization_count || raw.inactiveAuthorizationCount || 0,
    ),
    compatibilityMode: Boolean(raw.compatibility_mode || raw.compatibilityMode),
    summary: raw.summary || "",
    changeReason: raw.change_reason || raw.changeReason || "",
    changeNotes: raw.change_notes || raw.changeNotes || "",
    rollbackRecoveryPlan:
      raw.rollback_recovery_plan || raw.rollbackRecoveryPlan || "",
    recommendedActions: Array.isArray(recommendedActions)
      ? [...recommendedActions].filter(Boolean)
      : [],
    affectedAgents: Array.isArray(affectedAgents)
      ? affectedAgents.map(normalizePublicationImpactAgent)
      : [],
    metadata:
      raw.metadata && typeof raw.metadata === "object" ? raw.metadata : {},
    actorUserId: raw.actor_user_id || raw.actorUserId || "",
    actorUserEmail: raw.actor_user_email || raw.actorUserEmail || "",
    createdAt: raw.created_at || raw.createdAt || null,
  };
};

export const normalizeSubagentTenantGovernanceSummary = (raw = null) => {
  if (!raw || typeof raw !== "object") return null;
  const rawFilters = raw.event_filters || raw.eventFilters || {};
  return {
    totalCapabilities: Number(
      raw.total_capabilities || raw.totalCapabilities || 0,
    ),
    compatibilityCapabilities: Number(
      raw.compatibility_capabilities || raw.compatibilityCapabilities || 0,
    ),
    hostOverrideCapabilities: Number(
      raw.host_override_capabilities || raw.hostOverrideCapabilities || 0,
    ),
    metadataAliasCapabilities: Number(
      raw.metadata_alias_capabilities || raw.metadataAliasCapabilities || 0,
    ),
    publicationMissingCount: Number(
      raw.publication_missing_count || raw.publicationMissingCount || 0,
    ),
    publicationNotLatestCount: Number(
      raw.publication_not_latest_count || raw.publicationNotLatestCount || 0,
    ),
    authorizationCount: Number(
      raw.authorization_count || raw.authorizationCount || 0,
    ),
    enabledAuthorizationCount: Number(
      raw.enabled_authorization_count || raw.enabledAuthorizationCount || 0,
    ),
    inactiveAuthorizationCount: Number(
      raw.inactive_authorization_count || raw.inactiveAuthorizationCount || 0,
    ),
    bridgeRemovalReadyCapabilities: Number(
      raw.bridge_removal_ready_capabilities ||
        raw.bridgeRemovalReadyCapabilities ||
        0,
    ),
    bridgeRemovalBlockedCount: Number(
      raw.bridge_removal_blocked_count || raw.bridgeRemovalBlockedCount || 0,
    ),
    bridgeRemovalPendingCount: Number(
      raw.bridge_removal_pending_count || raw.bridgeRemovalPendingCount || 0,
    ),
    highRiskEventCount: Number(
      raw.high_risk_event_count || raw.highRiskEventCount || 0,
    ),
    confirmationRequiredEventCount: Number(
      raw.confirmation_required_event_count ||
        raw.confirmationRequiredEventCount ||
        0,
    ),
    compatibilityEventCount: Number(
      raw.compatibility_event_count || raw.compatibilityEventCount || 0,
    ),
    recentEventCount: Number(
      raw.recent_event_count || raw.recentEventCount || 0,
    ),
    actionTypeCounts: raw.action_type_counts || raw.actionTypeCounts || {},
    eventStageCounts: raw.event_stage_counts || raw.eventStageCounts || {},
    changeTypeCounts: raw.change_type_counts || raw.changeTypeCounts || {},
    riskLevelCounts: raw.risk_level_counts || raw.riskLevelCounts || {},
    filters: {
      definitionId: rawFilters.definition_id || rawFilters.definitionId || "",
      actionType: rawFilters.action_type || rawFilters.actionType || "",
      eventStage: rawFilters.event_stage || rawFilters.eventStage || "",
      changeType: rawFilters.change_type || rawFilters.changeType || "",
      riskLevel: rawFilters.risk_level || rawFilters.riskLevel || "",
      compatibilityMode:
        rawFilters.compatibility_mode || rawFilters.compatibilityMode || "",
      limit: Number(rawFilters.limit || 0),
      offset: Number(rawFilters.offset || 0),
    },
  };
};

export const publicationRiskLabel = (riskLevel = "") =>
  ({
    low: "低风险",
    medium: "中风险",
    high: "高风险",
  })[
    String(riskLevel || "")
      .trim()
      .toLowerCase()
  ] || "未知风险";

export const publicationChangeLabel = (changeType = "") =>
  ({
    initial_publish: "首次发布",
    rollout: "发布切换",
    rollback: "版本回滚",
    status_change: "状态变更",
    scope_change: "范围变更",
    metadata_update: "元数据更新",
    metadata_alias_freeze: "元数据别名冻结",
  })[
    String(changeType || "")
      .trim()
      .toLowerCase()
  ] || "发布变更";

export const compatibilityDetailLabel = (kind = "") =>
  ({
    host_override: "宿主绑定",
    metadata_alias: "遗留元数据别名",
  })[
    String(kind || "")
      .trim()
      .toLowerCase()
  ] || "兼容压力";

export const bridgeRemovalStatusLabel = (status = "") =>
  ({
    ready: "可删桥接",
    pending: "待收尾",
    blocked: "存在阻塞",
  })[
    String(status || "")
      .trim()
      .toLowerCase()
  ] || "待评估";

export const publicationEventStageLabel = (stage = "") =>
  ({
    previewed: "预演",
    executed: "已执行",
  })[
    String(stage || "")
      .trim()
      .toLowerCase()
  ] || "治理事件";
