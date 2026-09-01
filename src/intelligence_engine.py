from __future__ import annotations
from typing import Any
import pandas as pd


def build_intelligence(analysis: dict[str, Any], total_wards: int | None = None) -> dict[str, Any]:
    s = analysis["summary"]
    findings: list[dict[str, Any]] = []
    recs: list[dict[str, Any]] = []

    def add_finding(fid, priority, area, finding, evidence_ref, confidence, recommendation):
        findings.append({"id": fid, "priority": priority, "area": area, "finding": finding,
                         "evidence_ref": evidence_ref, "confidence": confidence,
                         "recommendation": recommendation})

    if s.get("distinct_wards", 0) > 0:
        if total_wards:
            coverage = s["ward_coverage_pct"] or 0
            add_finding("F-001", "High" if coverage < 90 else "Normal", "Coverage",
                        f"{s['distinct_wards']:,} of {total_wards:,} configured wards are represented ({coverage:.1f}% coverage).",
                        "E-001", "High",
                        "Maintain the ward coverage position and investigate any reporting period where represented wards fall below the expected total.")
            if coverage < 100:
                recs.append({"id":"R-001","priority":"High","recommendation":"Investigate wards not represented in the reporting dataset before treating corridor coverage as complete.","evidence_ref":"E-001","confidence":"High"})
        else:
            add_finding("F-001", "Normal", "Coverage",
                        f"{s['distinct_wards']:,} distinct wards are represented, but total expected wards have not been configured.",
                        "E-001", "High", "Enter the official ward total for the municipality to calculate coverage.")
            recs.append({"id":"R-001","priority":"Normal","recommendation":"Configure the municipality's official total ward count to enable coverage measurement.","evidence_ref":"E-001","confidence":"High"})

    status = analysis.get("status", pd.DataFrame())
    if not status.empty:
        top = status.iloc[0]
        add_finding("F-002", "Normal", "Case status",
                    f"{top['value']} is the largest recorded status, representing {int(top['cases']):,} cases ({top['share_pct']:.1f}%).",
                    "E-002", "High", "Review the status mix against operational targets and investigate any unusually large unresolved or pending categories.")
        unresolved_terms = {"open", "pending", "in progress", "active", "new"}
        unresolved = status[status["value"].astype(str).str.lower().isin(unresolved_terms)]
        if not unresolved.empty:
            n = int(unresolved["cases"].sum())
            share = n / s["records"] * 100 if s["records"] else 0
            add_finding("F-003", "High" if share >= 20 else "Normal", "Unresolved workload",
                        f"{n:,} cases ({share:.1f}%) are in statuses commonly associated with unresolved or active work.",
                        "E-003", "Medium", "Prioritise review of active/unresolved cases, ageing and service-level exposure.")
            recs.append({"id":"R-002","priority":"High" if share >= 20 else "Normal","recommendation":"Review active/unresolved cases by age, priority, ward and owner to identify operational backlog and escalation needs.","evidence_ref":"E-003","confidence":"Medium"})

    channel = analysis.get("channel", pd.DataFrame())
    if not channel.empty:
        top = channel.iloc[0]
        add_finding("F-004", "Normal", "Channel",
                    f"{top['value']} is the dominant channel with {int(top['cases']):,} cases ({top['share_pct']:.1f}%).",
                    "E-004", "High", "Monitor demand concentration in the dominant channel and confirm capacity is aligned to observed demand.")

    cat1 = analysis.get("category1", pd.DataFrame())
    if not cat1.empty:
        top = cat1.iloc[0]
        add_finding("F-005", "Normal", "Service demand",
                    f"{top['value']} is the leading Case Category 1 with {int(top['cases']):,} cases ({top['share_pct']:.1f}%).",
                    "E-005", "High", "Use the leading demand category to focus operational capacity and review whether its resolution performance differs from other categories.")

    dates = analysis.get("dates", {})
    if dates.get("available"):
        add_finding("F-006", "Normal", "Time pattern",
                    f"The peak case-creation hour is {dates['peak_hour']:02d}:00 with {dates['peak_hour_cases']:,} cases.",
                    "E-006", "High", "Compare staffing and operational availability around the peak demand period.")

    quality = analysis.get("quality", pd.DataFrame())
    if not quality.empty:
        high = int((quality["severity"] == "High").sum()) if "severity" in quality else 0
        add_finding("F-007", "High" if high else "Normal", "Data quality",
                    f"{len(quality):,} data-quality findings were detected, including {high:,} high-severity finding(s).",
                    "E-007", "High", "Resolve or formally accept high-severity data-quality exceptions before using affected fields for high-stakes conclusions.")
        recs.append({"id":"R-003","priority":"High" if high else "Normal","recommendation":"Review the data-quality register and correct high-severity issues before final publication of the operational report.","evidence_ref":"E-007","confidence":"High"})

    fdf = pd.DataFrame(findings)
    rdf = pd.DataFrame(recs)

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

    # Concrete evidence values make the addendum independently reviewable.
    details = []
    def detail(eid, finding_id, metric, value, calculation):
        details.append({"evidence_id": eid, "finding_id": finding_id, "metric": metric, "value": value, "calculation": calculation})
    detail("E-001", "F-001", "Distinct wards", s.get("distinct_wards"), "Unique non-empty Ward Id values")
    detail("E-001", "F-001", "Configured total wards", s.get("total_wards"), "User-supplied official total")
    detail("E-001", "F-001", "Coverage %", s.get("ward_coverage_pct"), "Distinct wards / total wards × 100")
    detail("E-001", "F-001", "Missing/unrepresented wards", s.get("missing_wards"), "Total wards - distinct wards")
    if not status.empty:
        top = status.iloc[0]
        detail("E-002", "F-002", "Top status", top["value"], "Highest case-count status")
        detail("E-002", "F-002", "Top status cases", int(top["cases"]), "Frequency count")
        detail("E-002", "F-002", "Top status share %", float(top["share_pct"]), "Top status cases / total records × 100")
        unresolved_terms = {"open", "pending", "in progress", "active", "new"}
        unresolved = status[status["value"].astype(str).str.lower().isin(unresolved_terms)]
        if not unresolved.empty:
            n = int(unresolved["cases"].sum())
            detail("E-003", "F-003", "Unresolved/active cases", n, "Sum of configured active/unresolved status counts")
            detail("E-003", "F-003", "Unresolved/active share %", n / s["records"] * 100 if s["records"] else 0, "Unresolved/active cases / total records × 100")
    if not channel.empty:
        top = channel.iloc[0]
        detail("E-004", "F-004", "Dominant channel", top["value"], "Highest case-count channel")
        detail("E-004", "F-004", "Dominant channel cases", int(top["cases"]), "Frequency count")
        detail("E-004", "F-004", "Dominant channel share %", float(top["share_pct"]), "Channel cases / total records × 100")
    if not cat1.empty:
        top = cat1.iloc[0]
        detail("E-005", "F-005", "Leading category", top["value"], "Highest case-count Case Category 1")
        detail("E-005", "F-005", "Leading category cases", int(top["cases"]), "Frequency count")
        detail("E-005", "F-005", "Leading category share %", float(top["share_pct"]), "Category cases / total records × 100")
    if dates.get("available"):
        detail("E-006", "F-006", "Peak hour", f"{dates['peak_hour']:02d}:00", "Hour with maximum case count")
        detail("E-006", "F-006", "Peak-hour cases", dates["peak_hour_cases"], "Maximum hourly frequency")
    detail("E-007", "F-007", "Quality findings", len(quality), "Count of deterministic quality findings")
    detail("E-007", "F-007", "High severity findings", int((quality["severity"] == "High").sum()) if not quality.empty and "severity" in quality else 0, "Count of quality findings with severity=High")
    ddf = pd.DataFrame(details)

    qa = []
    valid_e = set(edf["id"].tolist())
    for _, row in fdf.iterrows():
        qa.append({"check":"Finding evidence reference","item":row["id"],"status":"PASS" if row["evidence_ref"] in valid_e else "FAIL"})
    for _, row in rdf.iterrows():
        qa.append({"check":"Recommendation evidence reference","item":row["id"],"status":"PASS" if row["evidence_ref"] in valid_e else "FAIL"})
    # Every evidence reference used by a finding should have concrete detail where possible.
    detailed_ids = set(ddf["evidence_id"].tolist())
    for eid in edf["id"]:
        qa.append({"check":"Evidence detail present","item":eid,"status":"PASS" if eid in detailed_ids else "FAIL"})
    qdf = pd.DataFrame(qa)
    return {"findings": fdf, "recommendations": rdf, "evidence": edf, "evidence_details": ddf, "qa": qdf}
