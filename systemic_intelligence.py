from __future__ import annotations
from typing import Any
import pandas as pd

FISHBONE_CATEGORIES = [
    "Governance and Accountability",
    "Process Design and Control",
    "Intergovernmental and Stakeholder Dependencies",
    "Resource Model and Capacity",
    "Infrastructure and Asset Constraint",
    "Data, Systems and Control Failure",
    "Policy, Standards and Compliance",
    "Communication and Feedback Loop",
]


def _clean(v: Any) -> str:
    s = str(v).strip()
    return "" if s.lower() in {"", "nan", "none", "nat"} else s


def _col(cols: dict[str, str | None], *keys: str) -> str | None:
    for k in keys:
        c = cols.get(k)
        if c:
            return c
    return None


def _source(analysis: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, str | None]]:
    df = analysis.get("source_df", pd.DataFrame())
    cols = analysis.get("columns", {}) or {}
    return (df.copy(), cols) if isinstance(df, pd.DataFrame) else (pd.DataFrame(), cols)


def _candidate_table(df: pd.DataFrame, cols: dict[str, str | None]) -> pd.DataFrame:
    specs = [
        ("category1", "Service / Category 1"),
        ("status_reason", "Status Reason"),
        ("case_result", "Case Result"),
        ("category2", "Service / Category 2"),
        ("category3", "Service / Category 3"),
    ]
    date_col = _col(cols, "created_on", "created", "date")
    city_col = _col(cols, "city", "location")
    ward_col = _col(cols, "ward_id", "ward")
    rows = []
    for key, label in specs:
        c = cols.get(key)
        if not c or c not in df.columns:
            continue
        s = df[c].map(_clean)
        generic = {"other", "unknown", "resolved", "closed", "open", "in progress", "normal", "medium", "low", "high", "yes", "no", "none", "n/a", "na"}
        s = s[(s != "") & (~s.str.lower().isin(generic))]
        if s.empty:
            continue
        for value, n in s.value_counts().head(20).items():
            mask = df[c].map(_clean).eq(str(value))
            dates = pd.to_datetime(df.loc[mask, date_col], errors="coerce") if date_col and date_col in df.columns else pd.Series(dtype="datetime64[ns]")
            months = int(dates.dt.to_period("M").nunique()) if not dates.empty else 0
            locations = int(df.loc[mask, city_col].map(_clean).replace("", pd.NA).nunique()) if city_col and city_col in df.columns else 0
            wards = int(df.loc[mask, ward_col].map(_clean).replace("", pd.NA).nunique()) if ward_col and ward_col in df.columns else 0
            share = float(n / len(df) * 100) if len(df) else 0.0
            recurring = months >= 3
            cross_area = locations >= 2 or wards >= 3
            material = int(n) >= max(10, int(round(len(df) * 0.01)))
            score = int(material) + int(recurring) + int(cross_area)
            rows.append({
                "dimension": label, "issue_pattern": str(value), "cases": int(n),
                "share_pct": round(share, 1), "active_months": months,
                "locations": locations, "wards": wards, "recurring": "Yes" if recurring else "No",
                "cross_area": "Yes" if cross_area else "No", "material": "Yes" if material else "No",
                "systemic_score": score,
            })
    if not rows:
        return pd.DataFrame(columns=["dimension","issue_pattern","cases","share_pct","active_months","locations","wards","recurring","cross_area","material","systemic_score"])
    return pd.DataFrame(rows).sort_values(["systemic_score","cases","active_months"], ascending=[False,False,False]).reset_index(drop=True)


def _gate(candidates: pd.DataFrame, df: pd.DataFrame, date_col: str | None) -> tuple[str, str]:
    if candidates.empty:
        return "HOLD", "No repeatable issue pattern could be identified from the available fields."
    top = candidates.iloc[0]
    if int(top["systemic_score"]) >= 3:
        return "PASS", "At least one material, recurring and cross-area issue pattern is visible in the historical evidence."
    if int(top["systemic_score"]) >= 2:
        return "REVIEW", "A recurring or cross-area pattern is visible, but the available evidence does not yet satisfy all systemicity signals."
    return "HOLD", "Observed concentration is insufficient to classify the issue as systemic; treat it as an operational observation pending more evidence."


def _category_signals(row: pd.Series, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    quality = analysis.get("quality", pd.DataFrame())
    qtext = " ".join(quality.astype(str).fillna("").values.ravel()).lower() if isinstance(quality, pd.DataFrame) else ""
    cases = int(row.get("cases", 0) or 0)
    recurring = row.get("recurring") == "Yes"
    cross = row.get("cross_area") == "Yes"
    signals = {
        "Governance and Accountability": (recurring and cross, "Repeated pattern across the historical period and multiple areas; ownership/escalation should be verified."),
        "Process Design and Control": (recurring, "The same issue pattern recurs across multiple months; workflow and control points require verification."),
        "Intergovernmental and Stakeholder Dependencies": (cross, "The pattern spans multiple locations/wards; shared dependencies should be checked where applicable."),
        "Resource Model and Capacity": (cases >= 25 and recurring, "Sustained volume may indicate capacity pressure; staffing/resource evidence is required to confirm."),
        "Infrastructure and Asset Constraint": ("asset" in str(row.get("issue_pattern", "")).lower() or "infrastructure" in str(row.get("issue_pattern", "")).lower(), "The issue label itself contains an infrastructure/asset signal; asset records are required for confirmation."),
        "Data, Systems and Control Failure": ("data" in qtext or "coding" in qtext or "missing" in qtext, "Available quality evidence contains data/control exceptions; confirm whether they contribute to the issue."),
        "Policy, Standards and Compliance": ("sla" in qtext or "policy" in qtext or "compliance" in qtext, "Quality evidence references standards/SLA/policy controls; verify the applicable rule before assigning causality."),
        "Communication and Feedback Loop": ("description" in qtext or "narrative" in qtext or "communication" in qtext, "Quality evidence indicates narrative/communication gaps; verify whether feedback or closure communication is recurrent."),
    }
    out=[]
    for cat,(hit,signal) in signals.items():
        if hit:
            out.append({"fishbone_category":cat,"evidence_signal":signal,"evidence_strength":"Moderate","validation_status":"Hypothesis — requires validation"})
    return out


def build_systemic_investigation(analysis: dict[str, Any], period_label: str = "Historical source period") -> dict[str, Any]:
    """Evidence-gated systemic issue detector and Fishbone-compatible worksheet data.

    Historical source data is used to detect recurrence, materiality and cross-area impact.
    The output never labels a candidate cause as a confirmed root cause without validation.
    """
    df, cols = _source(analysis)
    if df.empty:
        empty = pd.DataFrame()
        return {"gate":"HOLD","gate_reason":"No source rows available.","candidates":empty,"fishbone":empty,"likely_causes":empty,"five_whys":empty,"actions":empty,"worksheet":empty,"summary":{"gate":"HOLD","candidate_count":0,"fishbone_available":False}}
    date_col = _col(cols, "created_on", "created", "date")
    candidates = _candidate_table(df, cols)
    gate, reason = _gate(candidates, df, date_col)
    if gate == "HOLD":
        return {"gate":gate,"gate_reason":reason,"candidates":candidates.head(10),"fishbone":pd.DataFrame(),"likely_causes":pd.DataFrame(),"five_whys":pd.DataFrame(),"actions":pd.DataFrame(),"worksheet":pd.DataFrame(),"summary":{"gate":gate,"candidate_count":len(candidates),"fishbone_available":False}}
    top = candidates.iloc[0]
    fishbone_rows = _category_signals(top, analysis)
    fishbone = pd.DataFrame(fishbone_rows)
    if fishbone.empty:
        fishbone = pd.DataFrame([{"fishbone_category":c,"evidence_signal":"No direct source evidence mapped","evidence_strength":"None","validation_status":"Not evidenced — do not infer"} for c in FISHBONE_CATEGORIES])
    likely = []
    for i, r in fishbone.head(3).iterrows():
        likely.append({"no":i+1,"likely_cause":r["fishbone_category"],"candidate_cause":r["evidence_signal"],"five_whys_validation":"Why 1–5 require process/operational evidence","evidence":r["evidence_strength"],"confirmed_validated_root_cause":"No"})
    likely_causes=pd.DataFrame(likely)
    five=[]
    for i in range(len(likely_causes)):
        five.append({"cause_no":i+1,"why_1":"Why does the recurring pattern occur? Validate against process evidence.","why_2":"Why does that condition persist? Validate against controls/ownership.","why_3":"Why is the control not preventing recurrence? Validate against SOP/process records.","why_4":"Why has the gap not been corrected? Validate governance/resources/dependencies.","why_5":"What evidence confirms the underlying cause? Must be independently verified.","status":"Open validation chain"})
    five_whys=pd.DataFrame(five)
    problem=f"Recurring {top['dimension']} pattern: {top['issue_pattern']} — {int(top['cases']):,} cases ({float(top['share_pct']):.1f}%), observed across {int(top['active_months'])} month(s) and {int(top['wards'])} ward(s)."
    actions=pd.DataFrame([{"corrective_preventive_action":"Validate the leading Fishbone hypotheses against operational/process evidence before assigning a root cause.","owner":"To be assigned","due_date":"To be assigned","RAG":"Amber","status":"Open","verification_evidence":"Process records / owner confirmation / supporting operational evidence","escalation_required":"Yes"}])
    worksheet=pd.DataFrame([{
        "Case / Matter Title":f"Systemic investigation — {top['issue_pattern']}","Reference Number":"System-generated investigation ID","Service Area":top["dimension"],"Location / Hotspot":f"{int(top['locations'])} locations / {int(top['wards'])} wards",
        "Date Opened":period_label,"Responsible Owner":"To be assigned","Problem Statement":problem,"Visible Symptoms":f"Recurring volume across {int(top['active_months'])} month(s); cross-area={top['cross_area']}; material={top['material']}",
        "Evidence Used":"Historical source rows; recurrence, concentration and geographic distribution checks","Confirmed Validated Root Cause":"No — validation required","Escalation Required":"Yes"}])
    return {"gate":gate,"gate_reason":reason,"candidates":candidates.head(10),"fishbone":fishbone,"likely_causes":likely_causes,"five_whys":five_whys,"actions":actions,"worksheet":worksheet,"summary":{"gate":gate,"candidate_count":len(candidates),"fishbone_available":True,"top_issue":str(top['issue_pattern']),"top_cases":int(top['cases']),"top_active_months":int(top['active_months'])}}
