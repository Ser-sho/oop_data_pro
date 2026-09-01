from __future__ import annotations
from typing import Any
import pandas as pd

AUDIENCE_GUIDANCE = {
    "Executive management": {
        "focus": ["decision-impact", "top findings", "risks", "actions"],
        "detail": "low",
        "max_findings": 5,
        "max_recommendations": 4,
        "tone": "concise, decision-oriented",
    },
    "Operations management": {
        "focus": ["coverage", "workload", "channels", "service demand", "exceptions", "actions"],
        "detail": "medium",
        "max_findings": 8,
        "max_recommendations": 6,
        "tone": "operational and action-oriented",
    },
    "Analyst": {
        "focus": ["metrics", "patterns", "data quality", "methodology", "evidence"],
        "detail": "high",
        "max_findings": 12,
        "max_recommendations": 8,
        "tone": "analytical and evidence-heavy",
    },
    "Custom": {
        "focus": [],
        "detail": "medium",
        "max_findings": 8,
        "max_recommendations": 6,
        "tone": "custom",
    },
}


def build_audience_view(intelligence: dict[str, Any], audience: str, requirements: str = "") -> dict[str, Any]:
    cfg = AUDIENCE_GUIDANCE.get(audience, AUDIENCE_GUIDANCE["Custom"]).copy()
    findings = intelligence.get("findings", pd.DataFrame()).copy()
    recommendations = intelligence.get("recommendations", pd.DataFrame()).copy()

    # Preserve evidence-backed ordering; prefer high-confidence items for executive views.
    if not findings.empty and "confidence" in findings.columns:
        rank = {"High": 0, "Medium": 1, "Low": 2}
        findings["_rank"] = findings["confidence"].map(rank).fillna(3)
        findings = findings.sort_values(["_rank"]).drop(columns=["_rank"])
    if not recommendations.empty and "confidence" in recommendations.columns:
        rank = {"High": 0, "Medium": 1, "Low": 2}
        recommendations["_rank"] = recommendations["confidence"].map(rank).fillna(3)
        recommendations = recommendations.sort_values(["_rank"]).drop(columns=["_rank"])

    findings = findings.head(cfg["max_findings"]).reset_index(drop=True)
    recommendations = recommendations.head(cfg["max_recommendations"]).reset_index(drop=True)

    return {
        "audience": audience,
        "guidance": cfg,
        "findings": findings,
        "recommendations": recommendations,
        "requirements": requirements.strip(),
    }
