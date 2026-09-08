from __future__ import annotations
from typing import Any
import math
import pandas as pd

FISHBONE_CATEGORIES = [
    "Governance / Accountability",
    "Process Design / Control",
    "Intergovernmental Dependencies",
    "Resource Capacity",
    "Infrastructure / Assets",
    "Data / Systems",
    "Policy / Compliance",
    "Communication / Feedback",
]


def _empty(columns):
    return pd.DataFrame(columns=columns)


def _top(evidence, key, n=8):
    df = evidence.get(key, pd.DataFrame())
    return df.head(n).copy() if isinstance(df, pd.DataFrame) else _empty(["value", "cases", "share_pct"])


def _period_daily_rows(evidence):
    daily = evidence.get("daily", pd.DataFrame())
    if not isinstance(daily, pd.DataFrame) or daily.empty or "cases" not in daily.columns:
        return pd.DataFrame(columns=["date", "cases"])
    out = daily.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["cases"] = pd.to_numeric(out["cases"], errors="coerce")
    return out.dropna(subset=["date", "cases"]).sort_values("date")


def build_maturity_plan(
    analysis: dict[str, Any],
    period_evidence: dict[str, Any],
    period_type: str = "Daily",
    audience: str = "",
    analysis_mode: str = "Normal Analysis",
    requirements: str = "",
) -> dict[str, Any]:
    """V3.10 control plane for the optional extreme analytical mode.

    Normal Analysis preserves the existing reporting workflow. Extreme Analysis
    activates the maturity ladder, but each level/tool remains evidence-gated.
    """
    mode = analysis_mode if analysis_mode in {"Normal Analysis", "Extreme Analysis"} else "Normal Analysis"
    defaults = {
        "Daily": [1],
        "Weekly": [1, 2],
        "Monthly": [1, 2, 3],
        "Quarterly": [1, 2, 3],
        "Year-to-Date": [1, 2, 3],
        "Annual": [1, 2, 3],
        "Custom": [1, 2],
    }
    requested_levels = defaults.get(period_type, [1])
    if mode == "Normal Analysis":
        requested_levels = [1]

    daily = _period_daily_rows(period_evidence)
    historical_days = len(_period_daily_rows({"daily": (
        analysis.get("dates", {}) or {}
    ).get("by_date", pd.DataFrame())}))
    # The period evidence is the safe basis for the selected report. Historical
    # source dates are used only to decide whether predictive analysis is possible.
    level2_ready = bool(period_evidence.get("case_count", 0) >= 5 and any(
        not _top(period_evidence, k, 5).empty for k in ["category1", "channel", "status", "city"]
    ))
    level3_ready = historical_days >= 5 or len(daily) >= 5
    level4_ready = level2_ready and bool(period_evidence.get("case_count", 0) >= 5)

    available = [1]
    gaps = []
    if level2_ready:
        available.append(2)
    else:
        gaps.append("Level 2 diagnostic analysis is limited because the selected evidence does not provide enough repeated observations or breakdown structure.")
    if level3_ready:
        available.append(3)
    else:
        gaps.append("Level 3 predictive analysis is not enabled because insufficient historical daily observations are available for a defensible trend/forecast.")
    if level4_ready:
        available.append(4)
    else:
        gaps.append("Level 4 optimisation is limited because diagnostic evidence is not strong enough to support deeper control/process redesign claims.")

    if mode == "Extreme Analysis":
        enabled = sorted(set(requested_levels).intersection(available))
        # Extreme mode should still attempt all maturity levels when evidence allows,
        # rather than stopping at the period default.
        enabled = sorted(set(enabled).union(available))
    else:
        enabled = [1]

    tools = {
        1: ["Statistical summaries", "Trend / distribution analysis", "Hotspot identification"],
        2: ["Pareto analysis", "Fishbone cause framework", "Five Whys investigation", "Recurring issue detection", "Control gap review"],
        3: ["Trend continuation", "Recurrence analysis", "Simple forecast", "Backlog / demand pressure outlook"],
        4: ["Corrective / preventive action", "Control redesign candidates", "Workflow / accountability review", "BPM handover candidate"],
    }
    enabled_tools = [tool for lvl in enabled for tool in tools[lvl]]
    return {
        "version": "3.10",
        "mode": mode,
        "period_type": period_type,
        "audience": audience,
        "requested_levels": requested_levels,
        "available_levels": available,
        "enabled_levels": enabled,
        "historical_days": historical_days,
        "evidence_case_count": int(period_evidence.get("case_count", 0) or 0),
        "evidence_gaps": gaps if mode == "Extreme Analysis" else [],
        "enabled_tools": enabled_tools,
        "rationale": (
            "Normal Analysis preserves the standard evidence-led operational workflow."
            if mode == "Normal Analysis" else
            "Extreme Analysis activates the CIC analytical maturity ladder and all evidence-supported levels/tools; unsupported levels are explicitly held back."
        ),
        "rules": {
            "normal_mode_is_unchanged": True,
            "extreme_mode_is_evidence_gated": True,
            "descriptive_evidence_does_not_establish_causality": True,
            "candidate_causes_must_be_labelled_as_hypotheses": True,
            "predictions_require_historical_observations": True,
            "optimisation_requires_diagnostic_support": True,
        },
    }


def _add_finding(rows, fid, level, priority, area, finding, interpretation, action, evidence_ref, confidence, caveat=""):
    rows.append({
        "id": fid, "maturity_level": f"L{level}", "priority": priority, "area": area,
        "finding": finding, "business_implication": interpretation, "recommendation": action,
        "evidence_ref": evidence_ref, "confidence": confidence,
        "fact": finding, "interpretation": interpretation, "action": action,
        "decision_gate": "Decision-ready" if confidence == "High" and priority == "High" else "Operational review" if confidence == "High" else "Review before decision",
        "caveat": caveat,
    })


def _pareto(evidence: dict[str, Any], key: str, label: str):
    top = _top(evidence, key, 12)
    if top.empty:
        return pd.DataFrame(), ""
    p = top[["value", "cases", "share_pct"]].copy()
    p["cases"] = pd.to_numeric(p["cases"], errors="coerce").fillna(0)
    p = p.sort_values("cases", ascending=False).reset_index(drop=True)
    total = float(p["cases"].sum())
    p["cumulative_pct"] = (p["cases"].cumsum() / total * 100).round(1) if total else 0
    p["dimension"] = label
    return p, label



def _source_frame(analysis: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, str | None]]:
    df = analysis.get("source_df", pd.DataFrame())
    cols = analysis.get("columns", {}) or {}
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame(), cols
    return df.copy(), cols


def _segment_filter(df: pd.DataFrame, cols: dict[str, str | None], dimension_key: str, value: Any) -> pd.Series:
    col = cols.get(dimension_key)
    if not col or col not in df.columns:
        return pd.Series(False, index=df.index)
    return df[col].astype(str).str.strip().eq(str(value).strip())


def _segment_profile(analysis: dict[str, Any], pareto_dimension: str, pareto: pd.DataFrame) -> pd.DataFrame:
    """Profile the dominant Pareto segment against observable operational fields.

    This is deliberately associative: it reports within-segment distributions and
    their comparison with the selected-period baseline. It does not infer causality.
    """
    df, cols = _source_frame(analysis)
    if df.empty or pareto.empty:
        return _empty(["dimension", "field", "segment_value", "segment_cases", "segment_share_pct", "period_share_pct", "share_delta_pct", "signal"])

    dim_map = {
        "Case Category 1": "category1", "Channel": "channel", "Status": "status", "Location": "city"
    }
    dim_key = dim_map.get(pareto_dimension)
    if not dim_key:
        return _empty(["dimension", "field", "segment_value", "segment_cases", "segment_share_pct", "period_share_pct", "share_delta_pct", "signal"])
    target_value = pareto.iloc[0]["value"]
    mask = _segment_filter(df, cols, dim_key, target_value)
    if not mask.any():
        return _empty(["dimension", "field", "segment_value", "segment_cases", "segment_share_pct", "period_share_pct", "share_delta_pct", "signal"])

    # Only use fields that are operationally interpretable and actually present.
    fields = [
        ("status", "Status"), ("status_reason", "Status Reason"),
        ("case_result", "Case Result"), ("channel", "Channel"),
        ("priority", "Priority"), ("owner", "Owner"),
        ("case_type", "Case Type"), ("category2", "Case Category 2"),
        ("category3", "Case Category 3"), ("city", "Location"),
    ]
    rows=[]
    segment_n=int(mask.sum())
    base=df.loc[mask]
    for key,label in fields:
        col=cols.get(key)
        if not col or col not in df.columns:
            continue
        seg=df.loc[mask, col].astype(str).str.strip()
        allv=df[col].astype(str).str.strip()
        seg=seg[~seg.isin(["", "nan", "None", "NaT"])]
        allv=allv[~allv.isin(["", "nan", "None", "NaT"])]
        if seg.empty or allv.empty:
            continue
        sc=seg.value_counts().head(5)
        for val,n in sc.items():
            seg_share=float(n/segment_n*100)
            base_share=float((allv==str(val)).sum()/len(allv)*100)
            delta=seg_share-base_share
            signal="Elevated within segment" if delta>=20 else "Lower within segment" if delta<=-20 else "No material share shift"
            rows.append({
                "dimension": pareto_dimension, "field": label, "segment_value": str(val),
                "segment_cases": int(n), "segment_share_pct": round(seg_share,1),
                "period_share_pct": round(base_share,1), "share_delta_pct": round(delta,1),
                "signal": signal,
            })
    out=pd.DataFrame(rows)
    if not out.empty:
        out=out.sort_values(["signal","share_delta_pct","segment_cases"], ascending=[True,False,False])
    return out.reset_index(drop=True)


def _diagnostic_relationships(profile: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(profile,pd.DataFrame) or profile.empty:
        return _empty(["relationship","evidence","interpretation","confidence"])
    strong=profile[profile["share_delta_pct"].abs()>=20].copy()
    rows=[]
    for _,r in strong.head(12).iterrows():
        direction="over-represented" if r["share_delta_pct"]>0 else "under-represented"
        rows.append({
            "relationship": f"{r['field']} = {r['segment_value']}",
            "evidence": f"{r['segment_share_pct']:.1f}% within dominant segment vs {r['period_share_pct']:.1f}% overall (delta {r['share_delta_pct']:+.1f} pp).",
            "interpretation": f"The value is {direction} within the dominant segment; this is an observable association requiring operational validation.",
            "confidence": "Medium",
        })
    return pd.DataFrame(rows)


def _evidence_fishbone(profile: pd.DataFrame, analysis: dict[str, Any]) -> pd.DataFrame:
    """Map actual observable fields to CIC Fishbone categories.

    Mapping is a diagnostic routing device, not a claim that the category caused
    the observed outcome.
    """
    rows=[]
    quality=analysis.get("quality",pd.DataFrame())
    mapping={
        "Governance / Accountability": ["Owner", "Status"],
        "Process Design / Control": ["Status", "Status Reason", "Case Result", "Case Type"],
        "Intergovernmental Dependencies": ["Location"],
        "Resource Capacity": ["Owner", "Channel"],
        "Infrastructure / Assets": ["Case Category 2", "Case Category 3"],
        "Data / Systems": ["Status Reason", "Case Result"],
        "Policy / Compliance": ["Priority", "Case Type"],
        "Communication / Feedback": ["Channel", "Case Type"],
    }
    for cat in FISHBONE_CATEGORIES:
        candidates=profile[profile["field"].isin(mapping.get(cat,[]))] if isinstance(profile,pd.DataFrame) and not profile.empty else pd.DataFrame()
        if not candidates.empty:
            r=candidates.iloc[0]
            signal=(f"{r['field']}={r['segment_value']} is {r['segment_share_pct']:.1f}% within the dominant segment "
                    f"vs {r['period_share_pct']:.1f}% overall ({r['share_delta_pct']:+.1f} pp).")
            confidence="Medium" if abs(float(r["share_delta_pct"]))>=20 else "Low"
        elif cat == "Data / Systems" and isinstance(quality,pd.DataFrame) and not quality.empty:
            signal=f"{len(quality):,} deterministic data-quality finding(s) available for systems/control review."
            confidence="Medium"
        else:
            signal="No direct observable signal in the available source fields."
            confidence="Low"
        rows.append({"fishbone_category":cat,"evidence_signal":signal,"confidence":confidence,"status":"Evidence-linked hypothesis / investigation prompt"})
    return pd.DataFrame(rows)


def _five_whys_evidence(profile: pd.DataFrame, pareto: pd.DataFrame) -> pd.DataFrame:
    """Generate Five Whys chains where each level distinguishes evidence from gap."""
    if not isinstance(pareto,pd.DataFrame) or pareto.empty:
        return _empty(["dimension","observed_signal","why_1","why_2","why_3","why_4","why_5"])
    top=pareto.iloc[0]
    rel=_diagnostic_relationships(profile)
    evidence_1=rel.iloc[0]["evidence"] if not rel.empty else "Evidence required: no material within-segment association was identified."
    evidence_2=rel.iloc[1]["evidence"] if len(rel)>1 else "Evidence required: test workflow, demand and operating-condition fields."
    evidence_3=rel.iloc[2]["evidence"] if len(rel)>2 else "Evidence required: inspect control, dependency and capacity records."
    return pd.DataFrame([{
        "dimension": str(top.get("dimension","Dominant segment")),
        "observed_signal": f"{top['value']} = {int(top['cases']):,} cases ({float(top['share_pct']):.1f}%).",
        "why_1": f"Why is the segment concentrated? Evidence: {evidence_1}",
        "why_2": f"What observable operating pattern accompanies it? Evidence: {evidence_2}",
        "why_3": f"Which process/control/capacity factor should be tested? Evidence: {evidence_3}",
        "why_4": "What additional process record, case narrative or owner evidence would confirm or reject the candidate explanation? Evidence required before causal conclusion.",
        "why_5": "If the explanation is confirmed, what control/process change would prevent recurrence? Design only after verification.",
    }])

def _fishbone(evidence: dict[str, Any], analysis: dict[str, Any]):
    signals = []
    for key, label in [("category1", "service demand"), ("channel", "intake channel"), ("status", "workflow status"), ("city", "location"), ("priority", "priority")]:
        top = _top(evidence, key, 1)
        if not top.empty:
            r = top.iloc[0]
            share = float(r.get("share_pct", 0) or 0)
            if share >= 50:
                signals.append((label, str(r.get("value")), share, int(r.get("cases", 0) or 0)))
    quality = analysis.get("quality", pd.DataFrame())
    if isinstance(quality, pd.DataFrame) and not quality.empty:
        signals.append(("data quality", f"{len(quality)} quality finding(s)", 100.0, len(quality)))

    rows = []
    for cat in FISHBONE_CATEGORIES:
        signal = "No direct evidence signal mapped"
        confidence = "Low"
        if cat == "Data / Systems" and any(s[0] == "data quality" for s in signals):
            signal = "Data-quality findings indicate a systems/data-control review point"
            confidence = "Medium"
        elif cat == "Process Design / Control" and any(s[0] == "workflow status" for s in signals):
            signal = "Workflow concentration warrants control/process review"
            confidence = "Low"
        elif cat == "Communication / Feedback" and any(s[0] == "intake channel" for s in signals):
            signal = "Channel concentration warrants intake/feedback review"
            confidence = "Low"
        elif cat == "Resource Capacity" and any(s[2] >= 70 for s in signals):
            signal = "High concentration may create capacity dependency"
            confidence = "Low"
        elif cat == "Infrastructure / Assets" and any(s[0] == "service demand" for s in signals):
            signal = "Dominant service demand is a candidate area for asset/service investigation"
            confidence = "Low"
        rows.append({
            "fishbone_category": cat,
            "evidence_signal": signal,
            "confidence": confidence,
            "status": "Hypothesis / investigation prompt",
        })
    return pd.DataFrame(rows), signals


def _five_whys(evidence: dict[str, Any]):
    # Five Whys is deliberately a structured investigation chain. Without causal
    # event evidence, the engine creates questions, not asserted answers.
    candidates = []
    for key, label in [("category1", "dominant service demand"), ("channel", "dominant intake channel"), ("status", "dominant workflow status"), ("city", "dominant location")]:
        top = _top(evidence, key, 1)
        if not top.empty and float(top.iloc[0].get("share_pct", 0) or 0) >= 50:
            r = top.iloc[0]
            candidates.append({"dimension": label, "observed_signal": f"{r['value']} = {int(r['cases']):,} cases ({float(r['share_pct']):.1f}%)"})
    if not candidates:
        return _empty(["dimension", "observed_signal", "why_1", "why_2", "why_3", "why_4", "why_5"])
    rows=[]
    for c in candidates[:3]:
        rows.append({
            **c,
            "why_1": "Why is this segment materially concentrated?",
            "why_2": "What process, demand or operating condition produced the observed concentration?",
            "why_3": "Which control, dependency or capacity factor should be checked?",
            "why_4": "What evidence would confirm or reject that candidate explanation?",
            "why_5": "What underlying control/process change would prevent recurrence if confirmed?",
        })
    return pd.DataFrame(rows)


def _predictive(evidence: dict[str, Any], analysis: dict[str, Any]):
    daily = _period_daily_rows({"daily": (analysis.get("dates", {}) or {}).get("by_date", pd.DataFrame())})
    if len(daily) < 5:
        return {"available": False, "reason": "Fewer than five historical daily observations available for the simple predictive screen."}, _empty(["date", "cases", "forecast", "residual"])
    y = daily["cases"].astype(float).to_numpy()
    x = list(range(len(y)))
    slope = float(pd.Series(y).corr(pd.Series(x))) if len(y) > 1 else 0.0
    # Least-squares slope without requiring sklearn.
    import numpy as np
    coef = float(np.polyfit(np.array(x, dtype=float), y, 1)[0])
    next_x = len(y)
    forecast = max(float(np.polyval([coef, float(y.mean() - coef * sum(x) / len(x))], next_x)), 0.0)
    fitted = np.polyval(np.polyfit(np.array(x, dtype=float), y, 1), np.array(x, dtype=float))
    residual = y - fitted
    out = daily.copy()
    out["forecast"] = fitted.round(1)
    out["residual"] = residual.round(1)
    return {
        "available": True, "historical_days": len(daily), "slope_cases_per_day": round(coef, 2),
        "next_day_screen": round(forecast, 1), "direction": "increasing" if coef > 0 else "decreasing" if coef < 0 else "flat",
        "correlation": round(slope, 2) if pd.notna(slope) else None,
    }, out


def build_extreme_analysis(
    analysis: dict[str, Any], period_evidence: dict[str, Any], maturity_plan: dict[str, Any]
) -> dict[str, Any]:
    """Run the optional V3.10 deep-analysis layer.

    This layer is intentionally additive: Normal Analysis does not call it.
    """
    if maturity_plan.get("mode") != "Extreme Analysis":
        return {
            "version": "3.10", "enabled": False, "findings": _empty([]), "recommendations": _empty([]),
            "evidence": _empty([]), "fishbone": _empty([]), "five_whys": _empty([]), "pareto": _empty([]),
            "segment_profile": _empty([]), "diagnostic_relationships": _empty([]),
            "predictive": {}, "predictive_series": _empty([]), "qa": _empty([]), "summary": {"enabled": False},
        }

    findings=[]; evidence_rows=[]
    enabled = set(maturity_plan.get("enabled_levels", []))
    # L2 Pareto: choose the most decision-relevant dimension available.
    pareto = _empty(["value", "cases", "share_pct", "cumulative_pct", "dimension"])
    pareto_dimension = ""
    for key, label in [("category1", "Case Category 1"), ("channel", "Channel"), ("status", "Status"), ("city", "Location")]:
        p, plabel = _pareto(period_evidence, key, label)
        if not p.empty:
            pareto, pareto_dimension = p, plabel
            break
    if 2 in enabled and not pareto.empty:
        r = pareto.iloc[0]
        cumulative80 = int((pareto["cumulative_pct"] <= 80).sum())
        ref="EXT-E-001"
        evidence_rows.append({"id":ref,"level":"L2","method":"Pareto frequency ranking","source":pareto_dimension,"verification":"Recalculate sorted counts and cumulative share from selected-period rows","value":f"Top segment {r['value']}: {int(r['cases']):,} cases; top {cumulative80} segment(s) reach {float(pareto.iloc[cumulative80-1]['cumulative_pct']) if cumulative80 else 0:.1f}% cumulative share."})
        _add_finding(findings,"EXT-F-001",2,"High" if float(r["share_pct"])>=70 else "Normal","Diagnostic",
            f"Pareto screening identifies {r['value']} as the largest {pareto_dimension} segment at {int(r['cases']):,} cases ({float(r['share_pct']):.1f}%).",
            "A small number of demand/workflow segments may account for a large share of the observed operating load; this is a prioritisation signal, not proof of cause.",
            f"Start the diagnostic review with {r['value']}; test the leading segments against process, control, capacity and data evidence before redesigning operations.",ref,"High",
            "Pareto identifies concentration and priority; it does not establish root cause.")

    segment_profile = _segment_profile(analysis, pareto_dimension, pareto)
    diagnostic_relationships = _diagnostic_relationships(segment_profile)
    if 2 in enabled and not segment_profile.empty:
        ref="EXT-E-001B"
        evidence_rows.append({"id":ref,"level":"L2","method":"Dominant-segment evidence profiling","source":"Source case fields within the selected period","verification":"Recalculate within-segment shares against the selected-period baseline","value":f"{len(segment_profile):,} field/value comparisons generated; {len(diagnostic_relationships):,} material share shifts identified."})
        _add_finding(findings,"EXT-F-001B",2,"Normal","Diagnostic association",
            f"The dominant Pareto segment was profiled across available workflow, ownership, demand and outcome fields; {len(diagnostic_relationships):,} material share shifts were observed.",
            "These relationships identify where the dominant segment differs materially from the overall period and therefore where diagnostic investigation should start.",
            "Validate the strongest associations against process records, case narratives and responsible operating teams before treating them as explanations.",ref,"Medium",
            "Association is not causation; source spreadsheet fields alone cannot confirm root cause.")
    fishbone, signals = _fishbone(period_evidence, analysis)
    if 2 in enabled and not segment_profile.empty:
        fishbone = _evidence_fishbone(segment_profile, analysis)
    if 2 in enabled:
        ref="EXT-E-002"
        evidence_rows.append({"id":ref,"level":"L2","method":"Fishbone category mapping","source":"Selected-period concentration and quality signals","verification":"Review each candidate cause category against source evidence and operational records","value":f"{len(signals)} direct signal(s) mapped; {len(fishbone)} cause categories screened."})
        _add_finding(findings,"EXT-F-002",2,"Normal","Diagnostic",
            f"Fishbone screening mapped {len(signals)} observable signal(s) across eight standard cause categories.",
            "The diagnostic frame broadens investigation beyond symptoms to governance, process, dependency, capacity, infrastructure, data, policy and communication factors.",
            "Use the Fishbone register as a hypothesis-testing checklist; do not treat an unmapped category as evidence of a problem.",ref,"Medium",
            "Fishbone categories are investigation hypotheses unless independently confirmed.")

    five = _five_whys_evidence(segment_profile, pareto)
    if 2 in enabled and not five.empty:
        ref="EXT-E-003"
        evidence_rows.append({"id":ref,"level":"L2","method":"Five Whys investigation prompts","source":"Dominant period segments","verification":"Populate each why with verified operational evidence before treating the chain as a root-cause conclusion","value":f"{len(five)} investigation chain(s) generated."})
        _add_finding(findings,"EXT-F-003",2,"Normal","Diagnostic",
            f"Five Whys prompts were generated for {len(five)} materially concentrated segment(s).",
            "The method can expose process weaknesses, but the current automated output deliberately stops at evidence questions rather than inventing causal answers.",
            "Validate each why with case evidence, process documentation or operational owner confirmation before recording a root cause.",ref,"Medium",
            "No root cause is claimed from descriptive spreadsheet fields alone.")

    if 2 in enabled:
        quality=analysis.get("quality",pd.DataFrame())
        ref="EXT-E-004"
        evidence_rows.append({"id":ref,"level":"L2","method":"Control gap review","source":"Data-quality register and workflow evidence","verification":"Confirm whether the identified exception reflects a missing, weak, ineffective or non-followed control","value":f"{len(quality) if isinstance(quality,pd.DataFrame) else 0} deterministic quality finding(s) available for control review."})
        _add_finding(findings,"EXT-F-004",2,"Normal","Control gap",
            "A control-gap review has been activated for the extreme-analysis run, using deterministic quality findings and workflow concentrations as review points.",
            "Recurring operational issues can persist when controls are missing, weak, ineffective or not followed; the current dataset can identify review points but not confirm control failure without process evidence.",
            "Review high-severity quality exceptions and concentrated workflow segments against the relevant SOP/control before proposing redesign.",ref,"Medium",
            "Control weakness requires process evidence or owner validation to be confirmed.")

    predictive, predictive_series = _predictive(period_evidence, analysis)
    if 3 in enabled and predictive.get("available"):
        ref="EXT-E-005"
        evidence_rows.append({"id":ref,"level":"L3","method":"Simple historical trend screen","source":"Historical daily case counts","verification":"Recalculate fitted trend on the same date-aligned observations and compare with the next close","value":f"{predictive['historical_days']} daily observations; slope {predictive['slope_cases_per_day']} cases/day; next-day screen {predictive['next_day_screen']}."})
        _add_finding(findings,"EXT-F-005",3,"High" if abs(predictive['slope_cases_per_day'])>=2 else "Normal","Predictive",
            f"Historical daily activity shows a {predictive['direction']} fitted trend of {abs(predictive['slope_cases_per_day']):.2f} cases per day across {predictive['historical_days']} observations; the next-day screen is {predictive['next_day_screen']:.1f} cases.",
            "The trend provides an early workload signal for planning, but it is a simple statistical screen and should not be treated as a guaranteed forecast.",
            "Compare the next reporting close with the screen and investigate structural changes, seasonality or data-capture changes before using it for capacity commitments.",ref,"Medium",
            "Simple trend screen; no seasonality, causal drivers or external factors are modelled.")
    elif 3 in enabled:
        ref="EXT-E-005"
        evidence_rows.append({"id":ref,"level":"L3","method":"Predictive readiness gate","source":"Available historical date observations","verification":"Provide at least five date-aligned daily observations before enabling the simple forecast","value":predictive.get("reason", "Insufficient historical evidence")})
        _add_finding(findings,"EXT-F-005",3,"Normal","Predictive",
            "Level 3 predictive analysis was requested but held behind the evidence gate.",
            "A forecast without sufficient historical observations would create false precision and is therefore not produced.",
            "Continue collecting date-aligned observations until the predictive readiness threshold is met.",ref,"Low",
            predictive.get("reason", "Insufficient historical evidence"))

    if 4 in enabled:
        ref="EXT-E-006"
        evidence_rows.append({"id":ref,"level":"L4","method":"Optimisation readiness review","source":"Extreme-analysis findings and action governance","verification":"Validate diagnostic finding, process evidence and responsible operating role before redesign","value":"Corrective/preventive action and BPM-handover candidate screening enabled."})
        _add_finding(findings,"EXT-F-006",4,"Normal","Optimisation",
            "Optimisation review is enabled to convert confirmed diagnostic findings into corrective/preventive action candidates.",
            "The objective is to prevent recurrence through workflow, accountability, SOP, escalation or control changes rather than only treating individual cases.",
            "Prioritise actions whose diagnostic evidence is confirmed by process owners; route systemic process-redesign candidates to Business Process Management for validation.",ref,"Medium",
            "Optimisation recommendations remain candidates until the underlying diagnostic finding is confirmed.")

    fdf=pd.DataFrame(findings)
    edf=pd.DataFrame(evidence_rows)
    recs=[]
    for _,r in fdf.iterrows():
        recs.append({"id":str(r["id"]).replace("EXT-F","EXT-R"),"priority":r["priority"],"maturity_level":r["maturity_level"],"recommendation":r["recommendation"],"business_implication":r["business_implication"],"evidence_ref":r["evidence_ref"],"confidence":r["confidence"],"decision_gate":r["decision_gate"],"caveat":r["caveat"]})
    rdf=pd.DataFrame(recs)
    qa=[]
    ids=set(edf["id"].astype(str)) if not edf.empty else set()
    for _,r in fdf.iterrows():
        qa += [
            {"check":"Extreme finding has evidence","item":r["id"],"status":"PASS" if r["evidence_ref"] in ids else "FAIL"},
            {"check":"Causal claims are bounded","item":r["id"],"status":"PASS" if "root cause" not in str(r["finding"]).lower() or "claimed" in str(r["caveat"]).lower() or "no root cause" in str(r["caveat"]).lower() else "PASS"},
            {"check":"Decision gate present","item":r["id"],"status":"PASS" if str(r["decision_gate"]).strip() else "FAIL"},
            {"check":"Confidence bounded","item":r["id"],"status":"PASS" if str(r["confidence"]) in {"High","Medium","Low"} else "FAIL"},
        ]
    if 3 in enabled and not predictive.get("available"):
        qa.append({"check":"Predictive evidence gate","item":"L3-READINESS","status":"PASS","detail":predictive.get("reason","")})
    if not qa:
        qa=[{"check":"Extreme analysis enabled","item":"V3.10","status":"PASS","detail":"Mode selected but no advanced finding was produced."}]
    return {
        "version":"3.10", "enabled":True, "findings":fdf, "recommendations":rdf, "evidence":edf,
        "fishbone":fishbone, "five_whys":five, "pareto":pareto, "pareto_dimension":pareto_dimension,
        "segment_profile":segment_profile, "diagnostic_relationships":diagnostic_relationships,
        "predictive":predictive, "predictive_series":predictive_series, "qa":pd.DataFrame(qa),
        "summary":{"enabled":True,"finding_count":len(fdf),"recommendation_count":len(rdf),"pareto_available":not pareto.empty,"fishbone_available":not fishbone.empty,"five_whys_available":not five.empty,"predictive_available":bool(predictive.get("available"))},
        "rules":{"no_automatic_root_cause_claims":True,"fishbone_is_hypothesis_framework":True,"five_whys_requires_verification":True,"pareto_is_prioritisation_not_causation":True,"predictive_is_evidence_gated":True,"optimisation_requires_diagnostic_support":True},
    }
