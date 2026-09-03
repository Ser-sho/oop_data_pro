from __future__ import annotations
from typing import Any
import re
import pandas as pd


# The planner is deliberately deterministic. It chooses report content from
# available evidence, reporting period, requester/team and explicit focus.
# It does not invent metrics or silently treat missing fields as available.

CAPABILITY_LABELS = {
    "cases": "Case volume",
    "status": "Case status / workflow position",
    "coverage": "Geographic / ward coverage",
    "channel": "Channel mix",
    "time": "Time activity",
    "services": "Service / demand mix",
    "priority": "Priority mix",
    "location": "Municipality / area mix",
    "voc": "Voice of Citizen",
    "quality": "Data quality",
    "resolution": "Resolution position",
}

FOCUS_MAP = {
    "coverage": ["coverage", "ward", "geographic", "area", "municipality"],
    "operations": ["operation", "activity", "workflow", "productivity", "queue"],
    "resolution": ["resolve", "resolution", "closed", "outstanding", "active", "cancel"],
    "service": ["service", "demand", "category", "request"],
    "customer": ["citizen", "customer", "voc", "happiness", "satisfaction", "feedback"],
    "quality": ["quality", "validation", "data quality", "exception", "accuracy"],
    "risk": ["risk", "gap", "problem", "issue", "attention", "underperform"],
    "executive": ["executive", "management", "important", "summary", "decision"],
}

TEAM_DEFAULTS = {
    "operations": ["executive", "operations", "coverage", "service", "risk", "quality"],
    "entity": ["executive", "resolution", "risk", "quality", "service"],
    "management": ["executive", "risk", "operations", "quality"],
    "analyst": ["operations", "resolution", "coverage", "service", "quality", "customer"],
}


def _text(x: Any) -> str:
    return str(x or "").strip()


def _caps(analysis: dict[str, Any], voc_analysis: dict[str, Any] | None = None) -> set[str]:
    cols = analysis.get("columns", {}) or {}
    caps = {"cases"}
    if cols.get("status"):
        caps.update({"status", "resolution"})
    if cols.get("ward"):
        caps.add("coverage")
    if cols.get("channel"):
        caps.add("channel")
    if analysis.get("dates", {}).get("available"):
        caps.add("time")
    if any(cols.get(k) for k in ["category1", "category2", "category3", "category4", "category5"]):
        caps.add("services")
    if cols.get("priority"):
        caps.add("priority")
    if cols.get("city"):
        caps.add("location")
    if analysis.get("quality") is not None:
        caps.add("quality")
    if voc_analysis and voc_analysis.get("available"):
        caps.add("voc")
    return caps


def _requested_focus(instructions: str) -> list[str]:
    text = _text(instructions).lower()
    found = []
    for key, words in FOCUS_MAP.items():
        if any(w in text for w in words):
            found.append(key)
    return found


def _team_focus(team: str) -> list[str]:
    t = _text(team).lower()
    for key, vals in TEAM_DEFAULTS.items():
        if key in t:
            return vals[:]
    return ["executive", "operations", "risk", "quality"]


def _period_priority(period_type: str) -> list[str]:
    if period_type in {"Quarterly", "Annual", "Year-to-Date"}:
        return ["executive", "operations", "resolution", "service", "risk", "quality"]
    if period_type == "Monthly":
        return ["executive", "operations", "resolution", "service", "coverage", "risk", "quality"]
    return ["executive", "operations", "coverage", "service", "risk", "quality"]


def _section(title: str, purpose: str, capability: str | None, priority: int, required: bool = False) -> dict[str, Any]:
    return {
        "order": priority,
        "title": title,
        "purpose": purpose,
        "capability": capability,
        "required": required,
    }


def build_report_plan(
    analysis: dict[str, Any],
    department: str,
    requesting_team: str,
    period: Any,
    instructions: str = "",
    audience: str = "Executive management",
    voc_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    caps = _caps(analysis, voc_analysis)
    explicit = _requested_focus(instructions)
    defaults = _team_focus(requesting_team)
    period_priority = _period_priority(getattr(period, "period_type", "Daily"))
    focus = []
    for item in explicit + defaults + period_priority:
        if item not in focus:
            focus.append(item)

    # Translate focus into evidence-backed sections. A section is only proposed
    # as populated when the underlying capability exists.
    sections = [
        _section("Executive Summary", "State the period, scale, most important movement, risks and decisions.", "cases", 1, True),
    ]
    candidates = [
        ("Performance and Activity", "Explain volume and period movement against an available comparison.", "cases"),
        ("Geographic / Coverage Position", "Show geographic reach, coverage and gaps where a certified universe exists.", "coverage"),
        ("Case Workflow / Resolution Position", "Show active, resolved, cancelled and other workflow states when supported.", "resolution"),
        ("Service and Demand Mix", "Show leading service or demand categories without presenting them as departmental performance unless supported.", "services"),
        ("Channel and Time Activity", "Show intake mix and meaningful time patterns for the selected period.", "channel"),
        ("Location / Entity Performance", "Compare municipalities, regions or other available areas when the field supports it.", "location"),
        ("Priority / Risk Position", "Highlight priority concentration and operational risk signals.", "priority"),
        ("Voice of Citizen", "Use only supplied, date-aligned or explicitly labelled VoC evidence.", "voc"),
        ("Data Quality and Limitations", "Disclose exceptions that materially affect interpretation.", "quality"),
        ("Actions and Management Decisions", "Convert evidence-backed findings into owners, timing and success checks.", "quality",),
    ]
    rank = {name: i for i, name in enumerate(focus)}
    scored = []
    for idx, (title, purpose, cap) in enumerate(candidates, 2):
        if cap not in caps:
            continue
        focus_score = min(20, rank.get(next((f for f in focus if (f == cap or (f == "operations" and cap in {"cases", "channel"}) or (f == "risk" and cap == "quality"))), ""), 99))
        explicit_bonus = 0 if not explicit else (0 if any(f in {cap, "operations"} for f in explicit) else 3)
        scored.append((focus_score + explicit_bonus, idx, title, purpose, cap))
    scored.sort(key=lambda x: (x[0], x[1]))
    # Keep a concise management report; evidence depth belongs in the addendum.
    max_sections = 7 if getattr(period, "period_type", "Daily") in {"Daily", "Weekly"} else 9
    chosen = scored[: max(0, max_sections - 2)]
    for n, (_, _, title, purpose, cap) in enumerate(chosen, 2):
        sections.append(_section(title, purpose, cap, n))
    sections.append(_section("Actions and Management Decisions", "Summarize the highest-priority evidence-backed actions and decisions.", "quality", len(sections) + 1, True))
    sections.append(_section("Evidence and Method Note", "Point to the addendum for calculations, source registers, exceptions and traceability.", "quality", len(sections) + 1, True))

    # De-duplicate sections while preserving order.
    seen = set(); clean = []
    for s in sorted(sections, key=lambda x: x["order"]):
        if s["title"] not in seen:
            seen.add(s["title"]); clean.append(s)
    for i, s in enumerate(clean, 1):
        s["order"] = i

    gaps = []
    requested_caps = []
    for f in explicit:
        mapped = {
            "coverage": "coverage", "operations": "cases", "resolution": "resolution",
            "service": "services", "customer": "voc", "quality": "quality", "risk": "quality", "executive": "cases"
        }.get(f)
        if mapped and mapped not in requested_caps:
            requested_caps.append(mapped)
    for cap in requested_caps:
        if cap not in caps:
            gaps.append({"focus": cap, "status": "Not supported", "reason": f"Required analytical capability '{CAPABILITY_LABELS.get(cap, cap)}' was not identified in the supplied data."})

    # Main report vs addendum rule.
    addendum_items = [
        "source and file register", "field mapping / data dictionary", "period filter and denominators",
        "full distributions", "record-level or pseudonymised evidence where appropriate",
        "quality exceptions", "calculation checks", "finding-to-evidence traceability", "QA results"
    ]
    if "coverage" in caps:
        addendum_items += ["full accounted ward register", "missing-ward queue and ward-master exceptions"]

    period_label = getattr(period, "label", "Selected reporting period")
    return {
        "department": _text(department) or "Not specified",
        "requesting_team": _text(requesting_team) or "Not specified",
        "audience": _text(audience) or "Executive management",
        "period_type": getattr(period, "period_type", "Daily"),
        "period_label": period_label,
        "explicit_focus": explicit,
        "planning_focus": focus,
        "available_capabilities": sorted(caps),
        "capability_labels": {c: CAPABILITY_LABELS.get(c, c) for c in sorted(caps)},
        "sections": clean,
        "gaps": gaps,
        "main_report_rule": "Keep the main presentation concise: management decisions, material movements, risks and the evidence needed to understand them.",
        "addendum_rule": "Put detailed evidence and verification in the addendum so the main report is not overcrowded.",
        "addendum_items": addendum_items,
        "design_requirements": [
            "Professional hierarchy and consistent visual language",
            "Use charts only where they communicate a material pattern",
            "Avoid decorative charts with insufficient evidence",
            "Never fabricate a value for an unavailable field",
            "Show data caveats where they change interpretation",
            "Keep detailed tables and verification in the addendum",
        ],
    }


def plan_dataframe(plan: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame([
        {"Order": s["order"], "Section": s["title"], "Purpose": s["purpose"], "Capability": s.get("capability"), "Required": s["required"]}
        for s in plan.get("sections", [])
    ])
