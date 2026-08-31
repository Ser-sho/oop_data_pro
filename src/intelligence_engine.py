from __future__ import annotations
from typing import Any
import pandas as pd


def _fmt_pct(x: float) -> str:
    return f"{x:.1f}%"


def build_intelligence(analysis: dict[str, Any], total_wards: int | None = None) -> dict[str, Any]:
    s = analysis["summary"]
    findings: list[dict[str, Any]] = []
    recs: list[dict[str, Any]] = []

    # Coverage finding
    if s.get("distinct_wards", 0) > 0:
        if total_wards:
            coverage = s["ward_coverage_pct"] or 0
            findings.append({
                "id": "F-001", "priority": "High" if coverage < 90 else "Normal",
                "area": "Coverage", "finding": f"{s['distinct_wards']:,} of {total_wards:,} configured wards are represented ({coverage:.1f}% coverage).",
                "evidence_ref": "E-001", "confidence": "High",
                "recommendation": "Maintain the ward coverage position and investigate any reporting period where represented wards fall below the expected total."
            })
            if coverage < 100:
                recs.append({"id":"R-001","priority":"High","recommendation":"Investigate wards not represented in the reporting dataset before treating corridor coverage as complete.","evidence_ref":"E-001","confidence":"High"})
        else:
            findings.append({"id":"F-001","priority":"Normal","area":"Coverage","finding":f"{s['distinct_wards']:,} distinct wards are represented, but total expected wards have not been configured.","evidence_ref":"E-001","confidence":"High","recommendation":"Enter the official ward total for the municipality to calculate coverage."})
            recs.append({"id":"R-001","priority":"Normal","recommendation":"Configure the municipality's official total ward count to enable coverage measurement.","evidence_ref":"E-001","confidence":"High"})

    # Status / open workload
    status = analysis.get("status", pd.DataFrame())
    if not status.empty:
        top = status.iloc[0]
        findings.append({"id":"F-002","priority":"Normal","area":"Case status","finding":f"{top['value']} is the largest recorded status, representing {int(top['cases']):,} cases ({top['share_pct']:.1f}%).","evidence_ref":"E-002","confidence":"High","recommendation":"Review the status mix against operational targets and investigate any unusually large unresolved or pending categories."})

        unresolved_terms = {"open", "pending", "in progress", "active", "new"}
        unresolved = status[status["value"].astype(str).str.lower().isin(unresolved_terms)]
        if not unresolved.empty:
            n = int(unresolved["cases"].sum())
            share = n / s["records"] * 100 if s["records"] else 0
            findings.append({"id":"F-003","priority":"High" if share >= 20 else "Normal","area":"Unresolved workload","finding":f"{n:,} cases ({share:.1f}%) are in statuses commonly associated with unresolved or active work.","evidence_ref":"E-003","confidence":"Medium","recommendation":"Prioritise review of active/unresolved cases, ageing and service-level exposure."})
            recs.append({"id":"R-002","priority":"High" if share >= 20 else "Normal","recommendation":"Review active/unresolved cases by age, priority, ward and owner to identify operational backlog and escalation needs.","evidence_ref":"E-003","confidence":"Medium"})

    # Channel concentration
    channel = analysis.get("channel", pd.DataFrame())
    if not channel.empty and len(channel) >= 1:
        top = channel.iloc[0]
        findings.append({"id":"F-004","priority":"Normal","area":"Channel","finding":f"{top['value']} is the dominant channel with {int(top['cases']):,} cases ({top['share_pct']:.1f}%).","evidence_ref":"E-004","confidence":"High","recommendation":"Monitor demand concentration in the dominant channel and confirm capacity is aligned to observed demand."})

    # Demand concentration
    cat1 = analysis.get("category1", pd.DataFrame())
    if not cat1.empty:
        top = cat1.iloc[0]
        findings.append({"id":"F-005","priority":"Normal","area":"Service demand","finding":f"{top['value']} is the leading Case Category 1 with {int(top['cases']):,} cases ({top['share_pct']:.1f}%).","evidence_ref":"E-005","confidence":"High","recommendation":"Use the leading demand category to focus operational capacity and review whether its resolution performance differs from other categories."})

    # Peak hour
    dates = analysis.get("dates", {})
    if dates.get("available"):
        findings.append({"id":"F-006","priority":"Normal","area":"Time pattern","finding":f"The peak case-creation hour is {dates['peak_hour']:02d}:00 with {dates['peak_hour_cases']:,} cases.","evidence_ref":"E-006","confidence":"High","recommendation":"Compare staffing and operational availability around the peak demand period."})

    # Data quality as a management finding
    quality = analysis.get("quality", pd.DataFrame())
    if not quality.empty:
        high = int((quality["severity"] == "High").sum()) if "severity" in quality else 0
        findings.append({"id":"F-007","priority":"High" if high else "Normal","area":"Data quality","finding":f"{len(quality):,} data-quality findings were detected, including {high:,} high-severity finding(s).","evidence_ref":"E-007","confidence":"High","recommendation":"Resolve or formally accept high-severity data-quality exceptions before using affected fields for high-stakes conclusions."})
        recs.append({"id":"R-003","priority":"High" if high else "Normal","recommendation":"Review the data-quality register and correct high-severity issues before final publication of the operational report.","evidence_ref":"E-007","confidence":"High"})

    # Convert to dataframes
    fdf = pd.DataFrame(findings)
    rdf = pd.DataFrame(recs)

    # Evidence register: references point to deterministic analysis outputs.
    evidence = [
        {"id":"E-001","finding_ids":"F-001","source":"Ward Id","method":"Distinct non-empty ward values compared with configured total wards","verification":"Recalculate nunique and coverage percentage from the loaded dataset"},
        {"id":"E-002","finding_ids":"F-002","source":"Status","method":"Frequency distribution","verification":"Recalculate value counts from the loaded dataset"},
        {"id":"E-003","finding_ids":"F-003","source":"Status","method":"Configured unresolved/active status categories","verification":"Review the exact status values included in the rule"},
        {"id":"E-004","finding_ids":"F-004","source":"Channel","method":"Frequency distribution","verification":"Recalculate value counts from the loaded dataset"},
        {"id":"E-005","finding_ids":"F-005","source":"Case Category 1","method":"Frequency distribution","verification":"Recalculate value counts from the loaded dataset"},
        {"id":"E-006","finding_ids":"F-006","source":"Created On","method":"Group valid timestamps by hour","verification":"Recalculate hourly counts from parsed Created On values"},
        {"id":"E-007","finding_ids":"F-007","source":"Data-quality register","method":"Count deterministic quality rules and severities","verification":"Re-run quality checks against the loaded dataset"},
    ]
    edf = pd.DataFrame(evidence)

    # Lightweight QA: every finding and recommendation has evidence.
    qa = []
    valid_e = set(edf["id"].tolist())
    for _, row in fdf.iterrows():
        qa.append({"check":"Finding evidence reference","item":row["id"],"status":"PASS" if row["evidence_ref"] in valid_e else "FAIL"})
    for _, row in rdf.iterrows():
        qa.append({"check":"Recommendation evidence reference","item":row["id"],"status":"PASS" if row["evidence_ref"] in valid_e else "FAIL"})
    qdf = pd.DataFrame(qa)

    return {"findings": fdf, "recommendations": rdf, "evidence": edf, "qa": qdf}
