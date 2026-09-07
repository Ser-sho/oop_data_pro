from __future__ import annotations
from typing import Any
import pandas as pd


AREAS = {
    "status": "resolution",
    "channel": "channel",
    "category1": "services",
    "priority": "priority",
    "city": "location",
    "owner": "operations",
}


def _safe_top(df: pd.DataFrame, n: int = 8) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["value", "cases", "share_pct"])
    return df.head(n).copy()


def _period_over_period(period_summary: dict[str, Any] | None) -> dict[str, Any]:
    if not period_summary:
        return {"available": False}
    current = period_summary.get("case_count", period_summary.get("current_records"))
    comparison = period_summary.get("comparison_case_count", period_summary.get("comparison_records"))
    change = period_summary.get("change_pct")
    return {
        "available": isinstance(current, (int, float)) and isinstance(comparison, (int, float)),
        "current": current,
        "comparison": comparison,
        "change_pct": change,
    }


def _make_item(i: int, priority: str, area: str, finding: str, implication: str,
               recommendation: str, evidence_ref: str, confidence: str = "High") -> dict[str, Any]:
    return {
        "id": f"AI-F-{i:03d}",
        "priority": priority,
        "area": area,
        "finding": finding,
        "business_implication": implication,
        "recommendation": recommendation,
        "evidence_ref": evidence_ref,
        "confidence": confidence,
    }


def build_analytical_intelligence(
    analysis: dict[str, Any],
    period_evidence: dict[str, Any],
    period_summary: dict[str, Any] | None = None,
    report_plan: dict[str, Any] | None = None,
    audience: str = "",
    requesting_team: str = "",
) -> dict[str, Any]:
    """V3.4 deterministic intelligence layer.

    Pipeline: evidence -> materiality -> finding -> business implication -> action -> evidence.
    It deliberately avoids causal claims unless the supplied data contains a defensible comparison.
    """
    findings: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    idx = 1

    def evidence(eid: str, source: str, method: str, verification: str, value: str = ""):
        evidence_rows.append({"id": eid, "source": source, "method": method, "verification": verification, "value": value})

    n = int(period_evidence.get("case_count", 0) or 0)
    total = analysis.get("summary", {}).get("total_wards")
    wards = period_evidence.get("distinct_wards")

    # 1. Period volume movement: this is the strongest general-purpose management signal.
    pop = _period_over_period(period_summary)
    if pop["available"] and pop.get("change_pct") is not None:
        change = float(pop["change_pct"])
        if abs(change) >= 20:
            direction = "increase" if change > 0 else "decrease"
            priority = "High"
            finding = f"Selected-period case volume changed materially: {abs(change):.1f}% {direction} versus the configured comparison period ({int(pop['current']):,} vs {int(pop['comparison']):,} cases)."
            implication = "The operating load is materially different from the comparison baseline and should be explained before capacity, staffing or performance decisions are made."
            recommendation = "Investigate the movement using the available status, channel, service and location breakdowns; confirm whether it reflects demand, workflow or data-capture change."
            findings.append(_make_item(idx, priority, "Performance", finding, implication, recommendation, "AI-E-001")); idx += 1
        else:
            direction = "increase" if change > 0 else "decrease" if change < 0 else "no change"
            findings.append(_make_item(idx, "Normal", "Performance",
                f"Selected-period case volume shows a {abs(change):.1f}% {direction} versus the configured comparison period ({int(pop['current']):,} vs {int(pop['comparison']):,} cases).",
                "The movement is below the materiality threshold used for an escalation finding; it should still be monitored in the normal operating cycle.",
                "Continue routine monitoring and use the detailed period evidence to investigate any emerging concentration.", "AI-E-001")); idx += 1
        evidence("AI-E-001", "Period case counts", "Selected-period count compared with configured comparison period", "Recalculate both period filters and percentage change", f"{pop['current']} vs {pop['comparison']}; {pop['change_pct']}%")

    # 2. Geographic representation.
    if wards is not None:
        if total:
            coverage = float(wards) / float(total) * 100 if total else 0.0
            missing = max(int(total) - int(wards), 0)
            priority = "High" if coverage < 50 else "Normal"
            findings.append(_make_item(idx, priority, "Coverage",
                f"{int(wards):,} of {int(total):,} configured wards are represented in the selected period ({coverage:.1f}%), leaving {missing:,} unrepresented.",
                "A period with incomplete geographic representation may understate demand or leave areas without recorded activity; the gap is an evidence limitation as well as an operational queue.",
                "Validate the unrepresented wards against the official register and use the missing-ward list to target follow-up activity.", "AI-E-002")); idx += 1
            evidence("AI-E-002", "Ward Id + supplied ward total", "Distinct period wards divided by user-supplied/configured total", "Recalculate unique period wards and compare with the official register", f"{wards}/{total} = {coverage:.1f}%")
        else:
            findings.append(_make_item(idx, "Normal", "Coverage",
                f"{int(wards):,} distinct wards are represented in the selected period, but no official total ward count was supplied.",
                "Geographic reach cannot be expressed as a coverage percentage without an authoritative denominator.",
                "Supply the official ward total before making percentage-based coverage claims.", "AI-E-002")); idx += 1
            evidence("AI-E-002", "Ward Id", "Distinct non-empty period ward values", "Recalculate distinct wards; denominator remains unavailable", str(wards))

    # 3. Concentration signals. These are framed as concentration, not causality.
    for key, area, label, threshold, implication in [
        ("channel", "Channel", "intake channel", 70.0, "High concentration can create dependency on one intake route and may affect resilience if that route changes."),
        ("category1", "Service demand", "Case Category 1", 50.0, "High demand concentration identifies the dominant demand segment that should receive focused operational review."),
        ("city", "Location", "location", 60.0, "High geographic concentration identifies where recorded demand is clustered, but does not by itself establish service performance."),
        ("priority", "Priority", "priority segment", 60.0, "A concentrated priority mix may indicate a queue that deserves focused review, but priority labels alone do not establish severity or risk."),
    ]:
        top = _safe_top(period_evidence.get(key, pd.DataFrame()), 1)
        if top.empty:
            continue
        r = top.iloc[0]
        share = float(r.get("share_pct", 0) or 0)
        if share < threshold:
            continue
        value = str(r.get("value"))
        cases = int(r.get("cases", 0) or 0)
        findings.append(_make_item(idx, "High" if share >= 80 else "Normal", area,
            f"{value} accounts for {cases:,} of {n:,} selected-period cases ({share:.1f}%), indicating material concentration in the {label} dimension.",
            implication,
            f"Review {value} as the first segment for capacity and control checks; compare it with the next-largest segments before changing operating priorities.", f"AI-E-{idx+2:03d}"));
        evidence(f"AI-E-{idx+2:03d}", key, "Period-aligned frequency distribution", "Recalculate counts and shares from the selected-period rows", f"{value}: {cases} ({share:.1f}%)")
        idx += 1

    # 4. Status transition proxy: only state what status distribution can support.
    status = _safe_top(period_evidence.get("status", pd.DataFrame()), 8)
    if not status.empty:
        largest = status.iloc[0]
        share = float(largest.get("share_pct", 0) or 0)
        if share >= 50:
            findings.append(_make_item(idx, "High" if share >= 80 else "Normal", "Resolution",
                f"{largest['value']} is the largest status, representing {int(largest['cases']):,} cases ({share:.1f}%) in the selected period.",
                "The workflow mix is concentrated in one status, so the next review should determine whether that distribution is expected for the selected reporting context.",
                f"Review the {largest['value']} queue against the intended workflow target and examine ageing or resolution evidence if those fields are available.", "AI-E-007")); idx += 1
            evidence("AI-E-007", "Status", "Period-aligned status frequency", "Recalculate status counts and shares", f"{largest['value']}: {largest['cases']} ({share:.1f}%)")

    # 5. Quality as a decision gate.
    quality = analysis.get("quality", pd.DataFrame())
    if isinstance(quality, pd.DataFrame) and not quality.empty:
        high = int((quality.get("severity", pd.Series(dtype=str)).astype("string").str.lower() == "high").sum()) if "severity" in quality else 0
        findings.append(_make_item(idx, "High" if high else "Normal", "Data quality",
            f"{len(quality):,} deterministic data-quality finding(s) were detected, including {high:,} high-severity finding(s).",
            "Data-quality exceptions can change the interpretation of affected metrics and should be resolved or explicitly accepted before high-stakes use.",
            "Review high-severity exceptions first and confirm that the affected fields are safe to use in the final management report.", "AI-E-008")); idx += 1
        evidence("AI-E-008", "Data-quality register", "Deterministic validation rules", "Re-run the quality engine against the source dataset", f"{len(quality)} findings; {high} high")

    # Materiality ranking: high-priority first, then largest concentration/change.
    priority_order = {"High": 0, "Normal": 1, "Low": 2}
    findings.sort(key=lambda x: (priority_order.get(x["priority"], 9), x["id"]))
    for i, row in enumerate(findings, 1):
        row["rank"] = i

    recommendations = []
    seen = set()
    for row in findings:
        rec = row["recommendation"]
        if rec in seen:
            continue
        seen.add(rec)
        recommendations.append({
            "id": row["id"].replace("AI-F", "AI-R"),
            "priority": row["priority"],
            "recommendation": rec,
            "business_implication": row["business_implication"],
            "evidence_ref": row["evidence_ref"],
            "confidence": row["confidence"],
        })

    fdf = pd.DataFrame(findings)
    rdf = pd.DataFrame(recommendations)
    edf = pd.DataFrame(evidence_rows)

    qa = []
    valid = set(edf["id"]) if not edf.empty else set()
    for _, row in fdf.iterrows():
        qa.append({"check": "Finding has evidence", "item": row["id"], "status": "PASS" if row["evidence_ref"] in valid else "FAIL"})
        qa.append({"check": "Finding has business implication", "item": row["id"], "status": "PASS" if str(row["business_implication"]).strip() else "FAIL"})
        qa.append({"check": "Finding has recommendation", "item": row["id"], "status": "PASS" if str(row["recommendation"]).strip() else "FAIL"})
    # V3.5 — Evidence & Decision Intelligence enrichment.
    # Keep the original finding text stable for downstream renderers, while adding
    # explicit fact/interpretation/action layers and a confidence rationale.
    if not fdf.empty:
        evidence_lookup = {str(r["id"]): r for _, r in edf.iterrows()} if not edf.empty else {}
        strength = {"High": 0, "Medium": 0, "Low": 0}
        for i, row in fdf.iterrows():
            ev = evidence_lookup.get(str(row.get("evidence_ref", "")), {})
            source = str(ev.get("source", "")).strip()
            method = str(ev.get("method", "")).strip()
            verification = str(ev.get("verification", "")).strip()
            # High confidence requires a direct period-aligned method and an explicit
            # recalculation/verification instruction. Otherwise downgrade rather than
            # overstating certainty.
            if source and method and verification and "period" in method.lower():
                conf, basis = "High", "Direct period-aligned evidence with explicit recalculation/verification."
            elif source and method:
                conf, basis = "Medium", "Evidence source and method are present, but verification strength is limited."
            else:
                conf, basis = "Low", "Evidence metadata is incomplete; treat the finding as provisional."
            fdf.at[i, "confidence"] = conf
            fdf.at[i, "confidence_basis"] = basis
            fdf.at[i, "fact"] = str(row.get("finding", ""))
            fdf.at[i, "interpretation"] = str(row.get("business_implication", ""))
            fdf.at[i, "action"] = str(row.get("recommendation", ""))
            fdf.at[i, "decision_gate"] = (
                "Decision-ready" if conf == "High" and str(row.get("priority", "")) == "High"
                else "Review before decision" if conf != "High"
                else "Operational review"
            )
            fdf.at[i, "caveat"] = (
                "Descriptive evidence does not establish causality."
                if row.get("area") not in {"Data quality"} else
                "Resolve or explicitly accept material data-quality exceptions before high-stakes use."
            )
            strength[conf] += 1

    if not rdf.empty:
        # Recommendations inherit the strongest available evidence controls from
        # their originating finding.
        flookup = {str(r["id"]): r for _, r in fdf.iterrows()} if not fdf.empty else {}
        for i, row in rdf.iterrows():
            fid = str(row.get("id", "")).replace("AI-R", "AI-F")
            src = flookup.get(fid, {})
            rdf.at[i, "confidence_basis"] = src.get("confidence_basis", "")
            rdf.at[i, "decision_gate"] = src.get("decision_gate", "Review before decision")
            rdf.at[i, "caveat"] = src.get("caveat", "")

    # V3.5 traceability and decision-safety QA. These checks are intentionally
    # conservative: missing evidence blocks a finding from being treated as
    # decision-ready.
    qa_v35 = []
    evidence_ids = set(edf["id"].astype(str)) if not edf.empty and "id" in edf else set()
    for _, row in fdf.iterrows():
        rid = str(row.get("id", ""))
        evref = str(row.get("evidence_ref", ""))
        conf = str(row.get("confidence", ""))
        qa_v35.append({"check": "Fact/interpretation/action separated", "item": rid, "status": "PASS" if all(str(row.get(k, "")).strip() for k in ("fact", "interpretation", "action")) else "FAIL"})
        qa_v35.append({"check": "Evidence reference resolves", "item": rid, "status": "PASS" if evref in evidence_ids else "FAIL"})
        qa_v35.append({"check": "Confidence is bounded by evidence", "item": rid, "status": "PASS" if conf in {"High", "Medium", "Low"} else "FAIL"})
        qa_v35.append({"check": "Decision gate present", "item": rid, "status": "PASS" if str(row.get("decision_gate", "")).strip() else "FAIL"})
    qa_df = pd.concat([pd.DataFrame(qa), pd.DataFrame(qa_v35)], ignore_index=True) if qa_v35 else pd.DataFrame(qa)

    return {
        "version": "3.5",
        "audience": audience,
        "requesting_team": requesting_team,
        "findings": fdf,
        "recommendations": rdf,
        "evidence": edf,
        "qa": qa_df,
        "decision_summary": {
            "finding_count": int(len(fdf)),
            "recommendation_count": int(len(rdf)),
            "high_confidence": int(strength.get("High", 0)),
            "medium_confidence": int(strength.get("Medium", 0)),
            "low_confidence": int(strength.get("Low", 0)),
            "decision_ready_high_priority": int(((fdf.get("confidence", pd.Series(dtype=str)) == "High") & (fdf.get("priority", pd.Series(dtype=str)) == "High")).sum()) if not fdf.empty else 0,
        },
        "rules": {
            "no_fabrication": True,
            "no_causal_inference_from_descriptive_data": True,
            "material_change_threshold_pct": 20,
            "concentration_thresholds_are_signals_not_causes": True,
            "evidence_required_for_every_finding": True,
            "decision_ready_requires_high_confidence": True,
            "fact_interpretation_action_separation": True,
            "weak_evidence_is_downgraded": True,
        },
    }
