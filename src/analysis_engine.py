from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import pandas as pd
import numpy as np


COLUMN_ALIASES = {
    "case_id": ["Case Number", "(Do Not Modify) Case"],
    "created_on": ["Created On"],
    "modified_on": ["(Do Not Modify) Modified On", "Modified On"],
    "status": ["Status"],
    "channel": ["Channel"],
    "case_type": ["Case Type"],
    "priority": ["Priority"],
    "owner": ["Owner"],
    "status_reason": ["Status Reason"],
    "case_result": ["Case Results"],
    "district": ["District Name"],
    "ward": ["Ward Id", "Ward Id Municipality Name"],
    "city": ["City"],
    "category1": ["Case Category 1"],
    "category2": ["Case Category 2"],
    "category3": ["Case Category 3"],
    "category4": ["Case Category 4"],
    "category5": ["Case Category 5"],
    "future_resolution": ["Future Resolution Date"],
    "commitment": ["Commitment Stages"],
    "description": ["Description"],
    "resolution_comments": ["Resolution Comments"],
}


def resolve_columns(df: pd.DataFrame) -> dict[str, str | None]:
    return {key: next((c for c in aliases if c in df.columns), None) for key, aliases in COLUMN_ALIASES.items()}


def _clean_cat(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip().replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})


def _top_counts(df: pd.DataFrame, col: str | None, n: int = 15) -> pd.DataFrame:
    if not col or col not in df.columns:
        return pd.DataFrame(columns=["value", "cases", "share_pct"])
    s = _clean_cat(df[col]).dropna()
    if s.empty:
        return pd.DataFrame(columns=["value", "cases", "share_pct"])
    out = s.value_counts().head(n).rename_axis("value").reset_index(name="cases")
    out["share_pct"] = (out["cases"] / len(df) * 100).round(2)
    return out


def _date_analysis(df: pd.DataFrame, col: str | None) -> dict[str, Any]:
    if not col or col not in df.columns:
        return {"available": False}
    dt = pd.to_datetime(df[col], errors="coerce")
    valid = dt.dropna()
    if valid.empty:
        return {"available": False}
    by_date = valid.dt.date.value_counts().sort_index().rename_axis("date").reset_index(name="cases")
    by_hour = valid.dt.hour.value_counts().sort_index().rename_axis("hour").reset_index(name="cases")
    return {
        "available": True,
        "min": valid.min(),
        "max": valid.max(),
        "by_date": by_date,
        "by_hour": by_hour,
        "peak_hour": int(by_hour.loc[by_hour["cases"].idxmax(), "hour"]),
        "peak_hour_cases": int(by_hour["cases"].max()),
    }


def _status_metrics(df: pd.DataFrame, col: str | None) -> pd.DataFrame:
    out = _top_counts(df, col, 20)
    if out.empty:
        return out
    return out


def _quality_findings(df: pd.DataFrame, cols: dict[str, str | None]) -> pd.DataFrame:
    findings: list[dict[str, Any]] = []
    rows = len(df)
    if rows == 0:
        return pd.DataFrame()
    # Business-critical fields for this operational dataset.
    for key in ["case_id", "created_on", "status", "channel", "case_type", "priority", "ward"]:
        col = cols.get(key)
        if col:
            n = int(df[col].isna().sum())
            if n:
                findings.append({"severity": "High" if key in {"case_id", "created_on", "status"} else "Medium", "area": key, "issue": "Missing values", "records": n, "detail": f"{n / rows:.1%} of records"})
    # Exact duplicate rows and duplicate case IDs.
    exact = int(df.duplicated().sum())
    if exact:
        findings.append({"severity": "High", "area": "record", "issue": "Exact duplicate rows", "records": exact, "detail": "Identical records"})
    cid = cols.get("case_id")
    if cid:
        dup_ids = int(df[cid].duplicated(keep=False).sum())
        if dup_ids:
            findings.append({"severity": "High", "area": "case_id", "issue": "Repeated case identifiers", "records": dup_ids, "detail": "Case identifiers occur more than once; inspect before deduplicating"})
    # Date parse failures.
    for key in ["created_on", "modified_on", "future_resolution"]:
        col = cols.get(key)
        if col:
            raw = df[col]
            parsed = pd.to_datetime(raw, errors="coerce")
            bad = int((raw.notna() & parsed.isna()).sum())
            if bad:
                findings.append({"severity": "High", "area": key, "issue": "Unparseable date/time", "records": bad, "detail": "Non-empty values could not be parsed"})
    return pd.DataFrame(findings)


def analyze_operations(df: pd.DataFrame, total_wards: int | None = None, municipality: str = "") -> dict[str, Any]:
    cols = resolve_columns(df)
    rows = len(df)
    valid_case_mask = pd.Series(True, index=df.index)
    if cols["case_id"]:
        valid_case_mask &= df[cols["case_id"]].notna()
    valid_cases = int(valid_case_mask.sum())

    ward_col = cols["ward"]
    wards = pd.Series(dtype="string")
    if ward_col:
        wards = _clean_cat(df[ward_col]).dropna()
    ward_count = int(wards.nunique()) if not wards.empty else 0
    ward_coverage = None
    missing_wards = None
    if total_wards and total_wards > 0:
        ward_coverage = round(ward_count / total_wards * 100, 2)
        missing_wards = max(total_wards - ward_count, 0)

    dates = _date_analysis(df, cols["created_on"])
    status = _top_counts(df, cols["status"], 10)
    channel = _top_counts(df, cols["channel"], 15)
    case_type = _top_counts(df, cols["case_type"], 15)
    priority = _top_counts(df, cols["priority"], 10)
    city = _top_counts(df, cols["city"], 15)
    cat1 = _top_counts(df, cols["category1"], 15)
    cat2 = _top_counts(df, cols["category2"], 15)
    cat3 = _top_counts(df, cols["category3"], 20)
    owner = _top_counts(df, cols["owner"], 15)

    # Simple, transparent operational flags. These are findings, not causal conclusions.
    insights: list[dict[str, Any]] = []
    if not status.empty:
        top = status.iloc[0]
        insights.append({"id": "OPS-001", "type": "status_mix", "finding": f"The largest case status is {top['value']} with {int(top['cases']):,} cases ({top['share_pct']:.1f}%).", "evidence": f"Status distribution from {rows:,} records."})
    if not channel.empty:
        top = channel.iloc[0]
        insights.append({"id": "OPS-002", "type": "channel_mix", "finding": f"{top['value']} is the dominant channel with {int(top['cases']):,} cases ({top['share_pct']:.1f}%).", "evidence": "Channel frequency calculation."})
    if ward_count:
        text = f"{ward_count:,} distinct wards are represented in the dataset."
        if total_wards:
            text += f" Against the configured {total_wards:,} total wards, represented-ward coverage is {ward_coverage:.1f}% and {missing_wards:,} wards are not represented in the dataset."
        insights.append({"id": "OPS-003", "type": "ward_representation", "finding": text, "evidence": "Distinct non-empty Ward Id values."})
    if not cat1.empty:
        top = cat1.iloc[0]
        insights.append({"id": "OPS-004", "type": "service_demand", "finding": f"The leading Case Category 1 is {top['value']} with {int(top['cases']):,} cases.", "evidence": "Case Category 1 frequency calculation."})
    if dates.get("available"):
        insights.append({"id": "OPS-005", "type": "time_pattern", "finding": f"The highest case-creation hour in the available data is {dates['peak_hour']:02d}:00 with {dates['peak_hour_cases']:,} cases.", "evidence": "Created On grouped by hour."})

    quality = _quality_findings(df, cols)
    return {
        "columns": cols,
        "summary": {
            "records": rows,
            "valid_cases": valid_cases,
            "invalid_case_records": rows - valid_cases,
            "distinct_wards": ward_count,
            "total_wards": total_wards,
            "ward_coverage_pct": ward_coverage,
            "missing_wards": missing_wards,
            "municipality": municipality,
        },
        "status": status,
        "channel": channel,
        "case_type": case_type,
        "priority": priority,
        "city": city,
        "category1": cat1,
        "category2": cat2,
        "category3": cat3,
        "owner": owner,
        "dates": dates,
        "quality": quality,
        "insights": pd.DataFrame(insights),
    }
