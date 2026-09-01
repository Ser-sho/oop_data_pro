
from __future__ import annotations
from typing import Any
import pandas as pd


def run_report_qa(
    analysis: dict[str, Any],
    intelligence: dict[str, Any],
    audience_view: dict[str, Any],
    template_assessment: dict[str, Any] | None = None,
    report_requirements: str = "",
) -> pd.DataFrame:
    checks = []

    def add(check, status, detail, severity="Info"):
        checks.append({
            "check": check,
            "status": status,
            "severity": severity,
            "detail": detail,
        })

    s = analysis.get("summary", {})
    records = int(s.get("records", 0) or 0)
    valid = int(s.get("valid_cases", 0) or 0)

    add(
        "Dataset loaded",
        "PASS" if records > 0 else "FAIL",
        f"{records:,} records available for analysis.",
        "Critical" if records == 0 else "Info",
    )

    add(
        "Valid-case count",
        "PASS" if 0 <= valid <= records else "FAIL",
        f"Valid cases={valid:,}; total records={records:,}.",
        "Critical" if not (0 <= valid <= records) else "Info",
    )

    total_wards = s.get("total_wards")
    distinct_wards = int(s.get("distinct_wards", 0) or 0)
    coverage = s.get("ward_coverage_pct")
    if total_wards:
        expected = round(distinct_wards / total_wards * 100, 2)
        ok = coverage is not None and abs(float(coverage) - expected) < 0.011
        add(
            "Ward coverage calculation",
            "PASS" if ok else "FAIL",
            f"Represented={distinct_wards:,}; configured total={int(total_wards):,}; reported={coverage}%; recalculated={expected}%.",
            "Critical" if not ok else "Info",
        )
        missing = s.get("missing_wards")
        expected_missing = max(int(total_wards) - distinct_wards, 0)
        ok2 = missing == expected_missing
        add(
            "Missing-ward calculation",
            "PASS" if ok2 else "FAIL",
            f"Reported={missing}; recalculated={expected_missing}.",
            "Critical" if not ok2 else "Info",
        )
    else:
        add("Ward coverage configuration", "WARNING", "No official total ward count was supplied for this run.", "Warning")

    # Intelligence evidence checks.
    iq = intelligence.get("qa", pd.DataFrame())
    if iq is not None and not iq.empty:
        fail_count = int((iq["status"] == "FAIL").sum()) if "status" in iq else 0
        add(
            "Finding/evidence traceability",
            "PASS" if fail_count == 0 else "FAIL",
            f"{len(iq) - fail_count:,} of {len(iq):,} traceability checks passed.",
            "Critical" if fail_count else "Info",
        )
    else:
        add("Finding/evidence traceability", "WARNING", "No traceability QA rows were produced.", "Warning")

    # Audience controls should not remove the underlying analytical evidence.
    findings = audience_view.get("findings", pd.DataFrame())
    recs = audience_view.get("recommendations", pd.DataFrame())
    add(
        "Audience view generated",
        "PASS" if isinstance(findings, pd.DataFrame) and isinstance(recs, pd.DataFrame) else "FAIL",
        f"Audience-specific findings={len(findings):,}; recommendations={len(recs):,}.",
        "Critical" if not isinstance(findings, pd.DataFrame) else "Info",
    )

    if template_assessment is not None:
        score = float(template_assessment.get("score", 0))
        add(
            "Template assessment",
            "PASS" if score >= 70 else "WARNING",
            f"Template coverage score={score:.1f}%.",
            "Info" if score >= 70 else "Warning",
        )
        if report_requirements.strip():
            reqs = template_assessment.get("requirements", [])
            unmet = sum(1 for r in reqs if str(r.get("status", "")).lower() in {"gap", "missing", "unsupported"})
            add(
                "Requirement coverage",
                "PASS" if unmet == 0 else "WARNING",
                f"{len(reqs):,} requirements assessed; {unmet:,} marked as gaps/unsupported.",
                "Info" if unmet == 0 else "Warning",
            )

    # Numerical sanity checks.
    for key in ("status", "channel", "case_type", "priority", "city", "category1"):
        table = analysis.get(key)
        if isinstance(table, pd.DataFrame) and not table.empty and "cases" in table.columns:
            bad = int((pd.to_numeric(table["cases"], errors="coerce").fillna(-1) < 0).sum())
            add(
                f"{key} counts non-negative",
                "PASS" if bad == 0 else "FAIL",
                f"{bad:,} negative/invalid count rows detected.",
                "Critical" if bad else "Info",
            )

    return pd.DataFrame(checks)


def qa_status(qa_df: pd.DataFrame) -> str:
    if qa_df is None or qa_df.empty:
        return "REVIEW REQUIRED"
    if "status" in qa_df.columns and (qa_df["status"] == "FAIL").any():
        return "REPORT BLOCKED"
    if "status" in qa_df.columns and (qa_df["status"] == "WARNING").any():
        return "REVIEW REQUIRED"
    return "READY FOR REVIEW"
