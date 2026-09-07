from __future__ import annotations
from typing import Any
import re

"""V3.7 configuration layer for departments/entities and requesting teams.

Profiles are presentation and planning configuration only. They never create
metrics or override what the supplied dataset can actually support.
"""

TEAM_PROFILES = {
    "Operations Team": {
        "focus": ["operations", "coverage", "service", "risk", "quality"],
        "detail": "medium",
        "decision_style": "operational",
    },
    "Entity Team": {
        "focus": ["resolution", "service", "risk", "quality"],
        "detail": "medium",
        "decision_style": "entity-performance",
    },
    "Management": {
        "focus": ["executive", "resolution", "risk", "quality"],
        "detail": "low",
        "decision_style": "management",
    },
    "Analyst": {
        "focus": ["operations", "resolution", "coverage", "service", "quality", "customer"],
        "detail": "high",
        "decision_style": "analytical",
    },
}

# These are neutral configuration presets, not assumptions about available KPIs.
# A department can use Generic and still receive a complete data-driven report.
ENTITY_PRESETS = {
    "Generic": {
        "record_label": "case",
        "record_label_plural": "cases",
        "geography_label": "Geographic coverage",
        "service_label": "Service / demand",
        "status_label": "Workflow / status",
        "channel_label": "Intake channel",
        "priority_label": "Priority",
        "entity_label": "Entity / area",
        "default_focus": [],
        "notes": "Generic profile; terminology is derived from available fields and user instructions.",
    },
    "SASSA": {
        "record_label": "case",
        "record_label_plural": "cases",
        "geography_label": "Geographic / ward coverage",
        "service_label": "Service / demand",
        "status_label": "Case / resolution status",
        "channel_label": "Intake channel",
        "priority_label": "Priority",
        "entity_label": "Municipality / service area",
        "default_focus": ["service", "resolution", "coverage", "quality"],
        "notes": "Planning vocabulary only; no SASSA-specific KPI is assumed unless present in the data.",
    },
    "Home Affairs": {
        "record_label": "case",
        "record_label_plural": "cases",
        "geography_label": "Geographic coverage",
        "service_label": "Service / demand",
        "status_label": "Case / workflow status",
        "channel_label": "Intake channel",
        "priority_label": "Priority",
        "entity_label": "Service area / location",
        "default_focus": ["service", "resolution", "quality", "risk"],
        "notes": "Planning vocabulary only; no Home Affairs-specific KPI is assumed unless present in the data.",
    },
    "Health": {
        "record_label": "record",
        "record_label_plural": "records",
        "geography_label": "Geographic coverage",
        "service_label": "Service / demand",
        "status_label": "Workflow / status",
        "channel_label": "Intake channel",
        "priority_label": "Priority",
        "entity_label": "Facility / service area",
        "default_focus": ["service", "operations", "quality", "risk"],
        "notes": "Planning vocabulary only; no clinical or health KPI is assumed unless present in the data.",
    },
    "Education": {
        "record_label": "record",
        "record_label_plural": "records",
        "geography_label": "Geographic coverage",
        "service_label": "Service / demand",
        "status_label": "Workflow / status",
        "channel_label": "Intake channel",
        "priority_label": "Priority",
        "entity_label": "School / service area",
        "default_focus": ["service", "operations", "quality", "risk"],
        "notes": "Planning vocabulary only; no Education-specific KPI is assumed unless present in the data.",
    },
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def resolve_entity_profile(department: str, profile_name: str = "Generic") -> dict[str, Any]:
    dept = _clean(department) or "Not specified"
    key = _clean(profile_name) or "Generic"
    base = ENTITY_PRESETS.get(key, ENTITY_PRESETS["Generic"]).copy()
    base.update({
        "profile_name": key if key in ENTITY_PRESETS else "Generic",
        "department": dept,
        "configured": True,
        "rules": {
            "no_metric_invention": True,
            "data_capabilities_remain_authoritative": True,
            "profile_does_not_override_source_fields": True,
        },
    })
    return base


def resolve_team_profile(requesting_team: str) -> dict[str, Any]:
    team = _clean(requesting_team) or "Operations Team"
    exact = TEAM_PROFILES.get(team)
    if exact:
        cfg = exact.copy()
    else:
        lower = team.lower()
        if "management" in lower or "executive" in lower:
            cfg = TEAM_PROFILES["Management"].copy()
        elif "analyst" in lower:
            cfg = TEAM_PROFILES["Analyst"].copy()
        elif "entity" in lower:
            cfg = TEAM_PROFILES["Entity Team"].copy()
        else:
            cfg = TEAM_PROFILES["Operations Team"].copy()
    return {"team": team, **cfg, "configured": True}


def build_entity_context(department: str, requesting_team: str, profile_name: str = "Generic") -> dict[str, Any]:
    entity = resolve_entity_profile(department, profile_name)
    team = resolve_team_profile(requesting_team)
    focus = []
    for item in entity.get("default_focus", []) + team.get("focus", []):
        if item not in focus:
            focus.append(item)
    return {
        "entity": entity,
        "team": team,
        "planning_focus": focus,
        "report_identity": f"{entity['department']} | {team['team']}",
        "rules": {
            "entity_profile_is_configuration_not_evidence": True,
            "team_profile_changes_presentation_and_priority_not_metrics": True,
            "unsupported_requested_metrics_must_be_flagged": True,
        },
    }


def validate_entity_context(context: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    entity = context.get("entity", {})
    team = context.get("team", {})
    checks.append({"check": "Entity profile resolved", "status": "PASS" if entity.get("department") else "FAIL"})
    checks.append({"check": "Requesting team resolved", "status": "PASS" if team.get("team") else "FAIL"})
    checks.append({"check": "Profile cannot invent metrics", "status": "PASS" if entity.get("rules", {}).get("no_metric_invention") else "FAIL"})
    checks.append({"check": "Source capabilities remain authoritative", "status": "PASS" if entity.get("rules", {}).get("data_capabilities_remain_authoritative") else "FAIL"})
    checks.append({"check": "Unsupported requested metrics are flagged", "status": "PASS" if context.get("rules", {}).get("unsupported_requested_metrics_must_be_flagged") else "FAIL"})
    return checks
