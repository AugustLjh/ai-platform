"""Tests for alerting, SLO tracking, and ops runbook structures."""

from __future__ import annotations

import pytest

from ai_runtime.core.agent_runtime.alerting import (
    ALL_ALERT_RULES,
    ALL_RUNBOOK_ENTRIES,
    ALL_SLO_DEFINITIONS,
    Alert,
    AlertManager,
    AlertSeverity,
    SLODefinition,
    SLOState,
    SLOTracker,
    build_grafana_dashboard,
    export_ops_prometheus_metrics,
    get_all_runbook_entries,
    get_runbook_entries,
    monitoring_export_status,
)


async def test_alert_manager_fires_when_threshold_exceeded():
    fired: list[Alert] = []

    async def sink(alert: Alert) -> None:
        fired.append(alert)

    manager = AlertManager(sinks=[sink])
    alerts = await manager.evaluate("workspace", {"expired_count": 15})

    assert len(alerts) >= 1
    rule_names = {a.rule_name for a in alerts}
    assert "workspace_expired_count_high" in rule_names
    assert fired


async def test_alert_manager_respects_cooldown():
    manager = AlertManager()
    first = await manager.evaluate("workspace", {"expired_count": 15})
    second = await manager.evaluate("workspace", {"expired_count": 15})

    assert len(first) >= 1
    assert len(second) == 0


async def test_alert_manager_does_not_fire_below_threshold():
    manager = AlertManager()
    alerts = await manager.evaluate("workspace", {"expired_count": 2})

    workspace_expired = [a for a in alerts if a.rule_name == "workspace_expired_count_high"]
    assert len(workspace_expired) == 0


async def test_alert_manager_handles_not_equal_condition():
    manager = AlertManager()
    alerts = await manager.evaluate("sandbox", {"isolation_status": "failed"})

    assert any(a.rule_name == "sandbox_isolation_degraded" for a in alerts)


async def test_alert_manager_handles_compound_and_condition():
    manager = AlertManager()
    alerts = await manager.evaluate("observability", {"db_configured": True, "db_reachable": False})

    assert any(a.rule_name == "observability_db_unavailable" for a in alerts)


async def test_alert_manager_does_not_fire_when_condition_not_met():
    manager = AlertManager()
    alerts = await manager.evaluate("observability", {"db_configured": True, "db_reachable": True})

    assert not any(a.rule_name == "observability_db_unavailable" for a in alerts)


async def test_alert_manager_acknowledge_and_resolve():
    manager = AlertManager()
    await manager.evaluate("workspace", {"expired_count": 15})

    assert len(manager.active_alerts()) >= 1
    assert manager.acknowledge("workspace_expired_count_high") is True
    assert manager.active_alerts()[0].acknowledged is True
    assert manager.resolve("workspace_expired_count_high") is True
    assert len(manager.active_alerts()) == 0


async def test_alert_manager_status_summary():
    manager = AlertManager()
    await manager.evaluate("workspace", {"expired_count": 15})

    summary = manager.status_summary()
    assert summary["active_alert_count"] >= 1
    assert summary["rules_configured"] == len(ALL_ALERT_RULES)
    assert summary["status"] in {"warning", "critical", "healthy"}


async def test_slo_tracker_records_and_detects_breach():
    tracker = SLOTracker()
    for _ in range(90):
        tracker.record("workspace_cleanup_success_rate", good=True)
    for _ in range(15):
        tracker.record("workspace_cleanup_success_rate", good=False)

    state = tracker.get("workspace_cleanup_success_rate")
    assert state is not None
    assert state.total_events == 105
    assert state.good_events == 90
    assert state.breached is True
    assert state.current_percent < 99.0


async def test_slo_tracker_healthy_when_above_target():
    tracker = SLOTracker()
    for _ in range(100):
        tracker.record("workspace_cleanup_success_rate", good=True)

    state = tracker.get("workspace_cleanup_success_rate")
    assert state is not None
    assert state.breached is False
    assert state.current_percent == 100.0


async def test_slo_tracker_snapshot_includes_all_definitions():
    tracker = SLOTracker()
    snapshot = tracker.snapshot()

    assert snapshot["slo_count"] == len(ALL_SLO_DEFINITIONS)
    assert snapshot["status"] == "healthy"
    assert snapshot["breached_count"] == 0


async def test_slo_tracker_subsystem_snapshot():
    tracker = SLOTracker()
    for _ in range(10):
        tracker.record("sandbox_execution_success_rate", good=True)

    snapshot = tracker.subsystem_snapshot("sandbox")
    assert snapshot["subsystem"] == "sandbox"
    assert snapshot["slo_count"] >= 1
    assert snapshot["status"] == "healthy"


async def test_slo_state_error_budget():
    definition = SLODefinition(
        name="test_slo",
        subsystem="test",
        metric="test_metric",
        target_percent=99.0,
    )
    state = SLOState(definition=definition)
    for _ in range(99):
        state.record(good=True)
    state.record(good=False)

    assert state.current_percent == 99.0
    assert state.error_budget_remaining == 0.0
    assert state.breached is False


async def test_runbook_entries_exist_for_all_subsystems():
    subsystems = {"workspace", "sandbox", "browser", "observability"}
    for subsystem in subsystems:
        entries = get_runbook_entries(subsystem)
        assert len(entries) >= 1, f"no runbook entries for {subsystem}"
        for entry in entries:
            assert entry["subsystem"] == subsystem
            assert entry["scenario"]
            assert entry["symptoms"]
            assert entry["diagnosis_steps"]
            assert entry["recovery_actions"]


async def test_all_runbook_entries_have_required_fields():
    entries = get_all_runbook_entries()
    assert len(entries) == len(ALL_RUNBOOK_ENTRIES)
    assert {entry["subsystem"] for entry in entries} >= {"workspace", "sandbox", "web", "browser", "observability"}
    for entry in entries:
        assert "subsystem" in entry
        assert "scenario" in entry
        assert "severity" in entry
        assert "symptoms" in entry
        assert "diagnosis_steps" in entry
        assert "recovery_actions" in entry


async def test_all_alert_rules_have_valid_structure():
    for rule in ALL_ALERT_RULES:
        assert rule.name
        assert rule.condition
        assert rule.severity in AlertSeverity
        assert rule.subsystem
        assert rule.cooldown_seconds > 0
        assert rule.description
        assert rule.recovery_actions


async def test_all_slo_definitions_have_valid_structure():
    for definition in ALL_SLO_DEFINITIONS:
        assert definition.name
        assert definition.subsystem
        assert definition.metric
        assert 0 < definition.target_percent <= 100
        assert definition.window_seconds > 0


async def test_alert_snapshot_is_json_serializable():
    manager = AlertManager()
    await manager.evaluate("workspace", {"expired_count": 15})

    snapshot = manager.snapshot()

    assert snapshot["active_alert_count"] >= 1
    assert snapshot["active"][0]["rule_name"] == "workspace_expired_count_high"
    assert snapshot["rules"][0]["name"]


async def test_prometheus_export_includes_alert_and_slo_metrics():
    manager = AlertManager()
    tracker = SLOTracker()
    await manager.evaluate("workspace", {"expired_count": 15})
    tracker.record("workspace_cleanup_success_rate", good=True)
    tracker.record("workspace_cleanup_success_rate", good=False)

    text = export_ops_prometheus_metrics(
        alert_manager=manager,
        slo_tracker=tracker,
        generated_at="2026-05-17T00:00:00+00:00",
    )

    assert "# TYPE agent_runtime_alerts_active gauge" in text
    assert 'agent_runtime_alert_active{rule="workspace_expired_count_high",severity="warning",subsystem="workspace"} 1' in text
    assert 'agent_runtime_slo_current_percent{metric="cleanup_success",slo="workspace_cleanup_success_rate",subsystem="workspace"} 50.0' in text
    assert "agent_runtime_slo_breached" in text


async def test_grafana_dashboard_contains_runtime_ops_panels():
    dashboard = build_grafana_dashboard(datasource_uid="prom-main")

    assert dashboard["uid"] == "agent-runtime-ops"
    assert dashboard["templating"]["list"][0]["name"] == "subsystem"
    expressions = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    ]
    assert "agent_runtime_alerts_active" in expressions
    assert any("agent_runtime_slo_current_percent" in expr for expr in expressions)
    assert all(panel["datasource"]["uid"] == "prom-main" for panel in dashboard["panels"])


async def test_monitoring_export_status_exposes_prometheus_and_grafana_paths(monkeypatch):
    monkeypatch.setenv("AGENT_GRAFANA_DATASOURCE_UID", "prod-prom")

    status = monitoring_export_status()

    assert status["prometheus"]["enabled"] is True
    assert status["prometheus"]["path"] == "/api/v1/agents/ops-status/metrics"
    assert status["grafana"]["path"] == "/api/v1/agents/ops-status/grafana-dashboard"
    assert status["grafana"]["datasource_uid"] == "prod-prom"
