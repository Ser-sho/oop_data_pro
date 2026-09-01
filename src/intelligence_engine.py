from __future__ import annotations
from typing import Any
import pandas as pd


def build_intelligence(analysis: dict[str, Any], total_wards: int | None = None) -> dict[str, Any]:
    s = analysis["summary"]
    findings, recs = [], []

    def add(fid, priority, area, finding, evidence, confidence, recommendation):
        findings.append({"id": fid, "priority": priority, "area": area, "finding": finding,
                         "evidence_ref": evidence, "confidence": confidence,
                         "recommendation": recommendation})

    wards = int(s.get("distinct_wards", 0) or 0)
    total = int(total_wards or s.get("total_wards") or 0)
    coverage = float(s.get("ward_coverage_pct") or 0)
    missing = int(s.get("missing_wards") or 0)
    if total:
        if missing == 0:
            add("F-001", "Normal", "Coverage",
                f"All {wards:,} of {total:,} configured wards are represented in the extract, giving {coverage:.1f}% coverage.",
                "E-001", "High",
                "Maintain the complete ward representation and repeat the same validation at the next close.")
        else:
            add("F-001", "High", "Coverage",
                f"{wards:,} of {total:,} configured wards are represented ({coverage:.1f}%), leaving {missing:,} wards unrepresented in the extract.",
                "E-001", "High",
                "Validate the unrepresented wards against the official ward register and assign a follow-up owner before the next close.")
            recs.append({"id":"R-001","priority":"High","recommendation":"Validate and assign every unrepresented ward before treating the corridor as fully covered.","evidence_ref":"E-001","confidence":"High"})
    else:
        add("F-001", "Normal", "Coverage",
            f"{wards:,} distinct wards are represented, but no official total ward count was supplied; coverage cannot be calculated.",
            "E-001", "High",
            "Supply the municipality's official ward total so represented and missing coverage can be measured.")

    status = analysis.get("status", pd.DataFrame())
    if not status.empty:
        top = status.iloc[0]
        top_share = float(top["share_pct"])
        add("F-002", "Normal", "Case status",
            f"{top['value']} is the largest status at {int(top['cases']):,} cases ({top_share:.1f}% of records).",
            "E-002", "High",
            "Use the status mix to focus the next operational review; compare the largest status with the intended workflow target rather than assuming it is a backlog.")
        if len(status) > 1:
            second = status.iloc[1]
            add("F-003", "Normal", "Status concentration",
                f"The two largest status groups account for {int(top['cases']) + int(second['cases']):,} cases ({top_share + float(second['share_pct']):.1f}%), so operational attention is concentrated in {top['value']} and {second['value']}.",
                "E-002", "High",
                f"Review {top['value']} and {second['value']} together in the operational queue and confirm whether their mix is expected.")

    channel = analysis.get("channel", pd.DataFrame())
    if not channel.empty:
        top = channel.iloc[0]
        share = float(top["share_pct"])
        add("F-004", "High" if share >= 80 else "Normal", "Channel",
            f"{top['value']} carries {int(top['cases']):,} cases ({share:.1f}%), making it the dominant intake route.",
            "E-004", "High",
            f"Protect capacity for {top['value']} during the observed reporting window and review whether the concentration is expected or creates a single-channel dependency.")
        if share >= 80:
            recs.append({"id":"R-002","priority":"High","recommendation":f"Review capacity and controls around {top['value']}; the channel carries {share:.1f}% of recorded cases.","evidence_ref":"E-004","confidence":"High"})

    cat1 = analysis.get("category1", pd.DataFrame())
    if not cat1.empty:
        top = cat1.iloc[0]
        add("F-005", "Normal", "Service demand",
            f"{top['value']} is the leading Case Category 1 with {int(top['cases']):,} cases ({float(top['share_pct']):.1f}%).",
            "E-005", "High",
            f"Use {top['value']} as the first demand segment for capacity and resolution review; compare its outcome mix with other major categories.")

    dates = analysis.get("dates", {})
    if dates.get("available"):
        start, end = dates["day_min_time"], dates["day_max_time"]
        span_hours = (end - start).total_seconds() / 3600
        add("F-006", "Normal", "Time pattern",
            f"Observed case creation ran from {start:%H:%M} to {end:%H:%M}; the peak hour was {dates['peak_hour']:02d}:00 with {dates['peak_hour_cases']:,} cases.",
            "E-006", "High",
            f"Protect capacity around {dates['peak_hour']:02d}:00 and use the addendum hourly table to review the full observed {span_hours:.1f}-hour activity window.")

    quality = analysis.get("quality", pd.DataFrame())
    if not quality.empty:
        high = int((quality["severity"] == "High").sum()) if "severity" in quality else 0
        add("F-007", "High" if high else "Normal", "Data quality",
            f"{len(quality):,} data-quality findings were detected, including {high:,} high-severity finding(s).",
            "E-007", "High",
            "Resolve or formally accept high-severity data-quality findings before using affected fields for high-stakes decisions.")
        if high:
            recs.append({"id":"R-003","priority":"High","recommendation":"Review and resolve high-severity data-quality exceptions before final circulation.","evidence_ref":"E-007","confidence":"High"})

    fdf, rdf = pd.DataFrame(findings), pd.DataFrame(recs)
    evidence = pd.DataFrame([
        {"id":"E-001","finding_ids":"F-001","source":"Ward Id","method":"Distinct non-empty ward values compared with configured total","verification":"Recalculate unique Ward Id values and coverage"},
        {"id":"E-002","finding_ids":"F-002;F-003","source":"Status","method":"Frequency distribution","verification":"Recalculate status counts and shares"},
        {"id":"E-004","finding_ids":"F-004","source":"Channel","method":"Frequency distribution","verification":"Recalculate channel counts and shares"},
        {"id":"E-005","finding_ids":"F-005","source":"Case Category 1","method":"Frequency distribution","verification":"Recalculate category counts and shares"},
        {"id":"E-006","finding_ids":"F-006","source":"Created On","method":"Reporting-date filter then group by hour","verification":"Filter Created On to reporting date and recalculate hourly counts"},
        {"id":"E-007","finding_ids":"F-007","source":"Data-quality register","method":"Deterministic quality rules","verification":"Re-run quality checks on the source data"},
    ])
    details=[]
    def d(e,f,m,v,c): details.append({"evidence_id":e,"finding_id":f,"metric":m,"value":v,"calculation":c})
    d("E-001","F-001","Distinct wards",wards,"Unique non-empty Ward Id values")
    d("E-001","F-001","Configured total wards",total or None,"User-supplied official total")
    d("E-001","F-001","Coverage %",coverage if total else None,"Distinct wards / total wards × 100")
    d("E-001","F-001","Missing wards",missing if total else None,"Total wards - distinct wards")
    if not status.empty:
        d("E-002","F-002","Top status",status.iloc[0]["value"],"Highest case-count status")
        d("E-002","F-002","Top status cases",int(status.iloc[0]["cases"]),"Frequency count")
        d("E-002","F-002","Top status share %",float(status.iloc[0]["share_pct"]),"Cases / total records × 100")
        if len(status)>1: d("E-002","F-003","Top two status share %",float(status.iloc[0]["share_pct"])+float(status.iloc[1]["share_pct"]),"Top two status shares added")
    if not channel.empty:
        d("E-004","F-004","Dominant channel",channel.iloc[0]["value"],"Highest case-count channel")
        d("E-004","F-004","Dominant channel cases",int(channel.iloc[0]["cases"]),"Frequency count")
        d("E-004","F-004","Dominant channel share %",float(channel.iloc[0]["share_pct"]),"Cases / total records × 100")
    if not cat1.empty:
        d("E-005","F-005","Leading category",cat1.iloc[0]["value"],"Highest case-count Case Category 1")
        d("E-005","F-005","Leading category cases",int(cat1.iloc[0]["cases"]),"Frequency count")
        d("E-005","F-005","Leading category share %",float(cat1.iloc[0]["share_pct"]),"Cases / total records × 100")
    if dates.get("available"):
        d("E-006","F-006","Observed start",dates["day_min_time"].strftime("%H:%M:%S"),"Minimum Created On timestamp on reporting date")
        d("E-006","F-006","Observed end",dates["day_max_time"].strftime("%H:%M:%S"),"Maximum Created On timestamp on reporting date")
        d("E-006","F-006","Peak hour",f"{dates['peak_hour']:02d}:00","Hour with maximum case count")
        d("E-006","F-006","Peak-hour cases",dates["peak_hour_cases"],"Maximum hourly frequency")
    d("E-007","F-007","Quality findings",len(quality),"Count of deterministic quality findings")
    d("E-007","F-007","High severity findings",int((quality["severity"]=="High").sum()) if not quality.empty and "severity" in quality else 0,"Count where severity=High")
    ddf=pd.DataFrame(details)
    qa=[]; valid=set(evidence["id"])
    for _,r in fdf.iterrows(): qa.append({"check":"Finding evidence reference","item":r["id"],"status":"PASS" if r["evidence_ref"] in valid else "FAIL"})
    for _,r in rdf.iterrows(): qa.append({"check":"Recommendation evidence reference","item":r["id"],"status":"PASS" if r["evidence_ref"] in valid else "FAIL"})
    for eid in evidence["id"]: qa.append({"check":"Evidence detail present","item":eid,"status":"PASS" if eid in set(ddf["evidence_id"]) else "FAIL"})
    return {"findings":fdf,"recommendations":rdf,"evidence":evidence,"evidence_details":ddf,"qa":pd.DataFrame(qa)}
