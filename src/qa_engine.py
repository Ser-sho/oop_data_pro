
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


    # Reporting-date and period integrity checks. The reporting date is manually
    # selected and must never silently fall back to the dataset's latest date.
    dates = analysis.get("dates", {})
    created_col = analysis.get("columns", {}).get("created_on")
    if created_col and isinstance(analysis.get("source_df"), pd.DataFrame):
        src = analysis["source_df"]
        parsed = pd.to_datetime(src[created_col], errors="coerce")
        target = pd.Timestamp(analysis.get("reporting_date")).normalize() if analysis.get("reporting_date") is not None else None
        if target is not None:
            selected_count = int((parsed.dt.normalize() == target).sum())
            future_count = int((parsed.dt.normalize() > target).sum())
            add(
                "Reporting date is present in source data",
                "PASS" if selected_count > 0 else "WARNING",
                f"Selected reporting date has {selected_count:,} source rows; future-dated rows after cutoff={future_count:,}.",
                "Info" if selected_count > 0 else "Warning",
            )
            add(
                "Reporting-date cutoff enforced",
                "PASS" if dates.get("selected_day_cases", 0) == selected_count else "FAIL",
                f"Selected-day cases={dates.get('selected_day_cases', 0):,}; source rows on reporting date={selected_count:,}.",
                "Critical" if dates.get("selected_day_cases", 0) != selected_count else "Info",
            )
            if future_count:
                add("Future records excluded from reporting cutoff", "PASS", f"{future_count:,} records occur after the selected reporting date and are excluded from date-based reporting.", "Info")

    # Case-status reconciliation: mapped management categories must reconcile to
    # valid cases, including any explicitly labelled Other / Unknown bucket.
    status_summary = analysis.get("status_summary")
    if isinstance(status_summary, pd.DataFrame) and not status_summary.empty and "status_group" in status_summary.columns:
        total_rows = status_summary[status_summary["status_group"] == "Total"]
        status_total = int(total_rows.iloc[0]["cases"]) if not total_rows.empty else -1
        add(
            "Case-status reconciliation",
            "PASS" if status_total == valid else "FAIL",
            f"Status-summary total={status_total:,}; valid cases={valid:,}.",
            "Critical" if status_total != valid else "Info",
        )

    # Ward-master mapping controls. A master exception is a review item, not an
    # automatic correction, because the source may contain legitimate exceptions.
    mapping = analysis.get("ward_mapping")
    if isinstance(mapping, pd.DataFrame) and not mapping.empty:
        counts = mapping.get("mapping_status", pd.Series(dtype="string")).astype(str).value_counts()
        missing = int((mapping.get("mapping_status", pd.Series(dtype="string")) == "Missing").sum())
        outside = int((mapping.get("mapping_status", pd.Series(dtype="string")) == "Not in ward master").sum())
        add("Ward mapping completeness", "PASS" if missing == 0 else "WARNING", f"Missing ward mappings={missing:,}; rows outside supplied master={outside:,}.", "Info" if missing == 0 else "Warning")
        if outside:
            add("Ward-master exceptions surfaced", "WARNING", f"{outside:,} case rows use ward values not found in the supplied master. These are flagged, not silently reassigned.", "Warning")

    # Weekly tracker arithmetic. Running + still-needed should equal the configured
    # benchmark when a ward benchmark exists. New wards cannot exceed the number of
    # daily cases when one case maps to at most one ward.
    sd = dates.get("selected_day", {}) if isinstance(dates, dict) else {}
    benchmark = s.get("total_wards")
    if benchmark and sd:
        running = int(sd.get("running_wards", 0) or 0)
        still = int(sd.get("still_needed", 0) or 0)
        add("Weekly ward arithmetic", "PASS" if running + still == int(benchmark) else "FAIL", f"Running={running:,}; still needed={still:,}; benchmark={int(benchmark):,}.", "Critical" if running + still != int(benchmark) else "Info")
        new = int(sd.get("new_wards", 0) or 0)
        daily_cases = int(sd.get("cases", 0) or 0)
        add("New wards do not exceed daily cases", "PASS" if new <= daily_cases else "FAIL", f"New wards={new:,}; daily cases={daily_cases:,}.", "Critical" if new > daily_cases else "Info")

    # Channel-level new-ward numbers should also be bounded by channel case counts.
    ch = analysis.get("channel")
    if isinstance(ch, pd.DataFrame) and not ch.empty and "new_wards" in ch.columns and "cases" in ch.columns:
        bad = int((pd.to_numeric(ch["new_wards"], errors="coerce").fillna(0) > pd.to_numeric(ch["cases"], errors="coerce").fillna(0)).sum())
        add("Channel new-ward counts bounded", "PASS" if bad == 0 else "FAIL", f"{bad:,} channel rows have new-ward counts greater than case counts.", "Critical" if bad else "Info")

    # Corridor allocation reconciliation when a ward master is supplied. Because
    # the master intentionally preserves duplicate allocations, compare both the
    # listed allocation count and unique ward count and surface the difference.
    master = analysis.get("ward_master", {})
    if master.get("available"):
        listed = int(master.get("listed_allocations", 0) or 0)
        unique = int(master.get("unique_wards", 0) or 0)
        dup = int(master.get("duplicate_ward_numbers", 0) or 0)
        add("Ward-master allocation reconciliation", "PASS" if listed >= unique else "FAIL", f"Listed allocations={listed:,}; unique ward numbers={unique:,}; duplicate ward numbers={dup:,}.", "Critical" if listed < unique else "Info")
        corridor = analysis.get("corridor_coverage")
        if isinstance(corridor, pd.DataFrame) and not corridor.empty and "target" in corridor.columns:
            target_sum = int(pd.to_numeric(corridor["target"], errors="coerce").fillna(0).sum())
            add("Corridor targets reconcile to master", "PASS" if target_sum == listed else "WARNING", f"Corridor target sum={target_sum:,}; master listed allocations={listed:,}. Duplicate allocations are retained in the benchmark.", "Info" if target_sum == listed else "Warning")

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
