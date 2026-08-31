from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class ProfileResult:
    summary: dict[str, Any]
    columns: pd.DataFrame
    issues: pd.DataFrame


def _is_date_like(series: pd.Series, name: str) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if any(token in name.lower() for token in ("date", "time", "created", "modified", "future")):
        parsed = pd.to_datetime(series, errors="coerce")
        return parsed.notna().mean() >= 0.60
    return False


def _suspicious_numeric(series: pd.Series) -> str:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return ""
    flags: list[str] = []
    if (s < 0).mean() > 0 and any(k in str(series.name).lower() for k in ("amount", "revenue", "quantity", "count", "number")):
        flags.append("negative values")
    q1, q3 = s.quantile([0.25, 0.75])
    iqr = q3 - q1
    if iqr > 0:
        outlier_count = int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())
        if outlier_count:
            flags.append(f"{outlier_count:,} IQR outliers")
    return "; ".join(flags)


def profile_dataframe(df: pd.DataFrame) -> ProfileResult:
    rows, cols = df.shape
    records = []
    issues = []

    for col in df.columns:
        s = df[col]
        missing = int(s.isna().sum())
        unique = int(s.nunique(dropna=True))
        inferred = "datetime" if _is_date_like(s, str(col)) else str(s.dtype)
        if pd.api.types.is_numeric_dtype(s):
            inferred = "numeric"
        elif pd.api.types.is_bool_dtype(s):
            inferred = "boolean"
        elif inferred != "datetime":
            inferred = "categorical/text" if unique <= max(50, rows * 0.05) else "text/identifier"

        suspicious = _suspicious_numeric(s) if pd.api.types.is_numeric_dtype(s) else ""
        if missing:
            issues.append({"severity": "Medium", "issue": "Missing values", "column": str(col), "records": missing, "detail": f"{missing / rows:.1%} missing"})
        if suspicious:
            issues.append({"severity": "Medium", "issue": "Suspicious numeric values", "column": str(col), "records": "", "detail": suspicious})
        if _is_date_like(s, str(col)):
            parsed = pd.to_datetime(s, errors="coerce")
            invalid = int(s.notna().sum() - parsed.notna().sum())
            if invalid:
                issues.append({"severity": "High", "issue": "Invalid date/time values", "column": str(col), "records": invalid, "detail": "Values could not be parsed as dates/times"})

        records.append({
            "column": str(col),
            "dtype": str(s.dtype),
            "inferred_type": inferred,
            "rows": rows,
            "missing": missing,
            "missing_pct": round(missing / rows * 100, 2) if rows else 0,
            "unique": unique,
            "non_null": int(s.notna().sum()),
        })

    duplicate_rows = int(df.duplicated().sum())
    if duplicate_rows:
        issues.append({"severity": "High", "issue": "Duplicate rows", "column": "(entire row)", "records": duplicate_rows, "detail": "Exact duplicate records detected"})

    summary = {
        "rows": rows,
        "columns": cols,
        "duplicate_rows": duplicate_rows,
        "total_missing": int(df.isna().sum().sum()),
        "columns_with_missing": int((df.isna().sum() > 0).sum()),
        "date_columns": int(sum(r["inferred_type"] == "datetime" for r in records)),
        "numeric_columns": int(sum(r["inferred_type"] == "numeric" for r in records)),
    }
    return ProfileResult(summary, pd.DataFrame(records), pd.DataFrame(issues))
