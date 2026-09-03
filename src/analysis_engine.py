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


def _normalize_ward_value(value: Any) -> str | None:
    """Normalize ward values while preserving a traceable representation.

    Numeric CRM ward IDs such as 79700077 are mapped to the ward number 77
    when a numeric ward master is supplied. Plain ward numbers remain unchanged.
    """
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    try:
        num = int(float(text))
        return str(num)
    except Exception:
        return text


def parse_ward_master_excel(path_or_file) -> dict[str, Any]:
    """Read the EMM-style two-sheet ward allocation workbook.

    Expected structure: one sheet per corridor, with CCA in column B and
    comma-separated ward numbers in column C. The parser intentionally keeps
    duplicate ward allocations rather than silently dropping them.
    """
    xl = pd.ExcelFile(path_or_file)
    records: list[dict[str, Any]] = []
    for sheet in xl.sheet_names:
        raw = pd.read_excel(path_or_file, sheet_name=sheet, header=None)
        for _, row in raw.iterrows():
            cca = row.iloc[1] if len(row) > 1 else None
            ward_text = row.iloc[2] if len(row) > 2 else None
            if pd.isna(cca) or pd.isna(ward_text):
                continue
            cca_text = str(cca).strip()
            if cca_text.upper() in {"CCA", "NONE", "NAN"}:
                continue
            import re
            wards = re.findall(r"\b\d{1,3}\b", str(ward_text))
            for ward in wards:
                records.append({"corridor": str(sheet).strip(), "cca": cca_text, "ward": ward})
    master = pd.DataFrame(records, columns=["corridor", "cca", "ward"])
    if master.empty:
        return {"available": False, "master": master, "listed_allocations": 0, "unique_wards": 0, "duplicate_wards": pd.DataFrame()}
    master["ward"] = master["ward"].map(_normalize_ward_value)
    dup = master[master["ward"].duplicated(keep=False)].sort_values("ward")
    return {
        "available": True,
        "master": master,
        "listed_allocations": int(len(master)),
        "unique_wards": int(master["ward"].nunique()),
        "duplicate_wards": dup,
        "duplicate_ward_numbers": int(dup["ward"].nunique()),
        "corridor_totals": master.groupby("corridor")["ward"].nunique().to_dict(),
        "cca_totals": master.groupby(["corridor", "cca"])["ward"].nunique().to_dict(),
    }


def _map_case_wards(df: pd.DataFrame, ward_col: str | None, ward_master: dict[str, Any] | None) -> pd.DataFrame:
    if not ward_col:
        return pd.DataFrame(index=df.index, columns=["ward_raw", "ward", "mapping_status", "corridor", "cca"])
    out = pd.DataFrame(index=df.index)
    out["ward_raw"] = df[ward_col]
    out["ward"] = df[ward_col].map(_normalize_ward_value)
    out["mapping_status"] = "Unmapped"
    out["corridor"] = pd.NA
    out["cca"] = pd.NA
    if not ward_master or not ward_master.get("available"):
        out.loc[out["ward"].notna(), "mapping_status"] = "Raw value only"
        return out
    master = ward_master["master"]
    valid = set(master["ward"].dropna().astype(str))
    # If a CRM value is not itself a master ward number, try the final three
    # digits (e.g. 79700077 -> 77) only when that produces a master match.
    def map_one(v):
        if v is None: return None, "Missing"
        if v in valid: return v, "Matched"
        digits = ''.join(ch for ch in str(v) if ch.isdigit())
        if len(digits) >= 3 and digits[-3:].lstrip('0') in valid:
            candidate = digits[-3:].lstrip('0') or '0'
            return candidate, "Matched via numeric suffix"
        return v, "Not in ward master"
    mapped = out["ward"].map(map_one)
    out["ward"] = mapped.map(lambda x: x[0])
    out["mapping_status"] = mapped.map(lambda x: x[1])
    lookup = master.drop_duplicates("ward").set_index("ward")
    out["corridor"] = out["ward"].map(lookup["corridor"])
    out["cca"] = out["ward"].map(lookup["cca"])
    return out


def _daily_ward_tracker(df: pd.DataFrame, created_col: str | None, case_mask: pd.Series, ward_map: pd.DataFrame, reporting_date, ward_master: dict[str, Any] | None, history: pd.DataFrame | None = None) -> dict[str, Any]:
    empty = pd.DataFrame(columns=["date", "cases", "daily_wards", "new_wards", "running_wards", "still_needed", "coverage_pct"])
    if not created_col or created_col not in df.columns or reporting_date is None:
        return {"available": False, "tracker": empty, "selected_day": {}, "ward_coverage": pd.DataFrame(), "missing_wards": pd.DataFrame()}
    dates = pd.to_datetime(df[created_col], errors="coerce")
    target = pd.Timestamp(reporting_date).normalize()
    week_start = target - pd.Timedelta(days=target.weekday())
    eligible = case_mask & dates.notna() & (dates.dt.normalize() >= week_start) & (dates.dt.normalize() <= target)
    work = pd.DataFrame({"date": dates.dt.date, "ward": ward_map["ward"], "corridor": ward_map["corridor"], "cca": ward_map["cca"]}, index=df.index)
    work = work.loc[eligible & work["ward"].notna()].copy()
    current_dates = set(work["date"]) if not work.empty else set()
    # Optional retained history lets separate daily uploads build a cumulative
    # reporting-week position without changing the current dataset metrics.
    if history is not None and not history.empty:
        h = history.copy()
        h["date"] = pd.to_datetime(h["date"], errors="coerce").dt.date
        h = h.dropna(subset=["date", "ward"])
        h = h[(pd.to_datetime(h["date"]).dt.normalize() >= week_start) & (pd.to_datetime(h["date"]).dt.normalize() <= target)]
        if not h.empty:
            work = pd.concat([h[["date","ward","corridor","cca"]], work[["date","ward","corridor","cca"]]], ignore_index=True).drop_duplicates(subset=["date","ward"])
    if work.empty:
        return {"available": True, "tracker": empty, "selected_day": {}, "ward_coverage": pd.DataFrame(), "missing_wards": pd.DataFrame()}
    daily = []
    seen: set[str] = set()
    history_case_counts = {}
    if history is not None and not history.empty and "daily_cases" in history.columns:
        hh = history.copy()
        hh["date"] = pd.to_datetime(hh["date"], errors="coerce").dt.date
        history_case_counts = hh.groupby("date")["daily_cases"].max().to_dict()
    total = int(ward_master.get("listed_allocations", 0)) if ward_master and ward_master.get("available") else None
    master = ward_master.get("master") if ward_master else None
    for d, g in work.groupby("date", sort=True):
        wards_today = set(g["ward"].astype(str))
        new = wards_today - seen
        seen |= wards_today
        running = len(seen)
        current_case_count = int((case_mask & dates.notna() & (dates.dt.date == d)).sum())
        cases_for_day = current_case_count if d in current_dates else int(history_case_counts.get(d, 0))
        daily.append({"date": d, "cases": cases_for_day, "daily_wards": len(wards_today), "new_wards": len(new), "running_wards": running, "still_needed": max(total-running,0) if total is not None else None, "coverage_pct": round(running/total*100,2) if total else None})
    tracker = pd.DataFrame(daily)
    # The tracker is intentionally management-facing: Daily wards is an analytical
    # component used internally, while the published movement table uses New wards,
    # Running wards and Still needed.
    if not tracker.empty and "daily_wards" in tracker.columns:
        tracker = tracker.drop(columns=["daily_wards"])
    selected = tracker[tracker["date"] == target.date()]
    selected_day = selected.iloc[0].to_dict() if not selected.empty else {"date": target.date(), "cases": 0, "new_wards": 0, "running_wards": int(len(seen)), "still_needed": max(total-len(seen),0) if total is not None else None, "coverage_pct": round(len(seen)/total*100,2) if total else None}
    prior_history_dates = set()
    if history is not None and not history.empty:
        hd = pd.to_datetime(history["date"], errors="coerce").dt.normalize()
        prior_history_dates = set(
            hd[(hd >= week_start) & (hd < target)].dropna().dt.date.tolist()
        )
    selected_day["ward_history_status"] = (
        "Baseline — no prior ward history supplied" if not prior_history_dates else "Prior ward history included"
    )
    # Pace is based on the remaining working days in the Monday-Friday reporting
    # week. It is a recommendation, not an observed value.
    if total is not None:
        remaining_workdays = max(0, 4 - target.weekday()) if target.weekday() <= 4 else 0
        remaining = int(selected_day.get("still_needed") or 0)
        selected_day["suggested_new_wards_per_remaining_day"] = (
            int(__import__("math").ceil(remaining / remaining_workdays))
            if remaining_workdays > 0 and remaining > 0 else 0
        )
        selected_day["remaining_workdays_in_week"] = remaining_workdays
    if master is not None and not master.empty:
        reached = set(seen)
        coverage = master.copy()
        coverage["covered"] = coverage["ward"].astype(str).isin(reached)
        case_counts = work.groupby("ward").size().to_dict()
        first_seen = work.groupby("ward")["date"].min().to_dict()
        coverage["cases"] = coverage["ward"].map(lambda w: int(case_counts.get(w,0)))
        coverage["first_case_date"] = coverage["ward"].map(first_seen)
        missing = coverage[~coverage["covered"]].copy()
    else:
        coverage = pd.DataFrame(); missing = pd.DataFrame()
    return {"available": True, "tracker": tracker, "selected_day": selected_day, "ward_coverage": coverage, "missing_wards": missing}


def _cca_daily_tracker(df: pd.DataFrame, created_col: str | None, case_mask: pd.Series, ward_map: pd.DataFrame, reporting_date, ward_master: dict[str, Any] | None, history: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build a reporting-week CCA tracker using unique new wards only.

    Management-facing fields intentionally omit Daily wards. New wards are the
    unique wards first seen in each CCA on each day of the selected Monday-Friday
    reporting week; running wards are cumulative unique wards within that CCA.
    """
    cols = ["date", "corridor", "cca", "cases", "new_wards", "running_wards", "running_display", "still_needed", "coverage_pct"]
    if not created_col or created_col not in df.columns or reporting_date is None or ward_map.empty or not ward_master or not ward_master.get("available"):
        return pd.DataFrame(columns=cols)
    dates = pd.to_datetime(df[created_col], errors="coerce")
    target = pd.Timestamp(reporting_date).normalize()
    week_start = target - pd.Timedelta(days=target.weekday())
    eligible = case_mask & dates.notna() & (dates.dt.normalize() >= week_start) & (dates.dt.normalize() <= target)
    work = pd.DataFrame({
        "date": dates.dt.date,
        "ward": ward_map["ward"],
        "corridor": ward_map["corridor"],
        "cca": ward_map["cca"],
    }, index=df.index).loc[eligible].copy()
    work = work.dropna(subset=["ward", "corridor", "cca"])
    if history is not None and not history.empty:
        h = history.copy()
        h["date"] = pd.to_datetime(h["date"], errors="coerce").dt.date
        h = h.dropna(subset=["date", "ward", "corridor", "cca"])
        h = h[(pd.to_datetime(h["date"]).dt.normalize() >= week_start) & (pd.to_datetime(h["date"]).dt.normalize() <= target)]
        if not h.empty:
            work = pd.concat([h[["date","ward","corridor","cca"]], work[["date","ward","corridor","cca"]]], ignore_index=True).drop_duplicates(subset=["date","ward","corridor","cca"])
    if work.empty:
        return pd.DataFrame(columns=cols)

    master = ward_master.get("master", pd.DataFrame()).copy()
    if master.empty:
        return pd.DataFrame(columns=cols)
    targets = master.groupby(["corridor", "cca"])["ward"].nunique().to_dict()
    rows = []
    for (corridor, cca), gcca in work.groupby(["corridor", "cca"], sort=True):
        seen = set()
        for d, gd in gcca.groupby("date", sort=True):
            wards_today = set(gd["ward"].astype(str))
            new = wards_today - seen
            seen |= wards_today
            target_cca = int(targets.get((corridor, cca), 0))
            running = len(seen)
            cases = int(gd.shape[0])
            rows.append({
                "date": d,
                "corridor": corridor,
                "cca": cca,
                "cases": cases,
                "new_wards": len(new),
                "running_wards": running,
                "running_display": f"{running}/{target_cca}" if target_cca else str(running),
                "still_needed": max(target_cca - running, 0) if target_cca else None,
                "coverage_pct": round(running / target_cca * 100, 2) if target_cca else None,
            })
    return pd.DataFrame(rows, columns=cols)


def _top_counts(df: pd.DataFrame, col: str | None, n: int = 15) -> pd.DataFrame:
    if not col or col not in df.columns:
        return pd.DataFrame(columns=["value", "cases", "share_pct"])
    s = _clean_cat(df[col]).dropna()
    if s.empty:
        return pd.DataFrame(columns=["value", "cases", "share_pct"])
    out = s.value_counts().head(n).rename_axis("value").reset_index(name="cases")
    out["share_pct"] = (out["cases"] / len(df) * 100).round(2)
    return out


def _date_analysis(df: pd.DataFrame, col: str | None, reporting_date=None, case_mask=None, ward_map=None, ward_master=None, history: pd.DataFrame | None = None) -> dict[str, Any]:
    if not col or col not in df.columns:
        return {"available": False}
    dt = pd.to_datetime(df[col], errors="coerce")
    if case_mask is None:
        case_mask = pd.Series(True, index=df.index)
    valid_all = dt.notna() & case_mask
    if reporting_date is None:
        target = dt[valid_all].max().normalize() if valid_all.any() else None
    else:
        target = pd.Timestamp(reporting_date).normalize()
    if not valid_all.any():
        return {"available": False}
    period = dt[valid_all & (dt.dt.normalize() <= target)] if target is not None else dt[valid_all]
    selected = period[period.dt.normalize() == target] if target is not None else period
    by_date = period.dt.date.value_counts().sort_index().rename_axis("date").reset_index(name="cases")
    by_hour = selected.dt.hour.value_counts().sort_index().rename_axis("hour").reset_index(name="cases")
    tracker = _daily_ward_tracker(df, col, case_mask, ward_map if ward_map is not None else pd.DataFrame(index=df.index, columns=["ward","corridor","cca"]), target, ward_master, history=history)
    if selected.empty:
        peak_hour = None; peak_cases = 0; min_time = None; max_time = None
    else:
        peak_hour = int(by_hour.loc[by_hour["cases"].idxmax(), "hour"]) if not by_hour.empty else None
        peak_cases = int(by_hour["cases"].max()) if not by_hour.empty else 0
        min_time = selected.min(); max_time = selected.max()
    return {
        "available": True, "min": period.min(), "max": period.max(), "full_min": dt[valid_all].min(), "full_max": dt[valid_all].max(),
        "by_date": by_date, "by_hour": by_hour, "peak_hour": peak_hour, "peak_hour_cases": peak_cases,
        "day_min_time": min_time, "day_max_time": max_time, "reporting_date": reporting_date,
        "selected_day_cases": int(len(selected)), "selected_day": tracker.get("selected_day", {}),
        "daily_tracker": tracker.get("tracker", pd.DataFrame()), "ward_coverage": tracker.get("ward_coverage", pd.DataFrame()),
        "missing_wards": tracker.get("missing_wards", pd.DataFrame()),
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


def _status_summary(df: pd.DataFrame, status_col: str | None, valid_case_mask: pd.Series) -> pd.DataFrame:
    labels = ["Active", "Resolved", "Cancelled"]
    if not status_col or status_col not in df.columns:
        return pd.DataFrame(columns=["status_group", "cases", "share_pct"])
    raw = df.loc[valid_case_mask, status_col].astype(str).str.strip()
    normalized = raw.str.lower()
    mapped = pd.Series("Other / Unknown", index=raw.index)
    mapped[normalized.eq("active")] = "Active"
    mapped[normalized.eq("resolved")] = "Resolved"
    mapped[normalized.eq("cancelled") | normalized.eq("canceled")] = "Cancelled"
    counts = mapped.value_counts()
    total = len(mapped)
    rows = [{"status_group": lab, "cases": int(counts.get(lab, 0)), "share_pct": round((counts.get(lab, 0) / total * 100) if total else 0, 2)} for lab in labels]
    other = int(counts.get("Other / Unknown", 0))
    if other:
        rows.append({"status_group":"Other / Unknown", "cases":other, "share_pct":round(other/total*100,2)})
    rows.append({"status_group":"Total", "cases":total, "share_pct":100.0 if total else 0.0})
    return pd.DataFrame(rows)

def analyze_operations(df: pd.DataFrame, total_wards: int | None = None, municipality: str = "", reporting_date=None, ward_master: dict[str, Any] | None = None, ward_history: pd.DataFrame | None = None) -> dict[str, Any]:
    cols = resolve_columns(df)
    rows = len(df)
    valid_case_mask = pd.Series(True, index=df.index)
    if cols["case_id"]:
        valid_case_mask &= df[cols["case_id"]].notna()
    valid_cases = int(valid_case_mask.sum())

    ward_map = _map_case_wards(df, cols["ward"], ward_master)
    dates = _date_analysis(df, cols["created_on"], reporting_date=reporting_date, case_mask=valid_case_mask, ward_map=ward_map, ward_master=ward_master, history=ward_history)
    # Management-facing ward coverage follows the reporting-week tracker.
    # This prevents older historical records from making a new week's running
    # total look already complete.
    selected_tracker = dates.get("selected_day", {}) if isinstance(dates, dict) else {}
    ward_count = int(selected_tracker.get("running_wards", 0) or 0)
    if not selected_tracker:
        if reporting_date is not None and cols["created_on"]:
            created = pd.to_datetime(df[cols["created_on"]], errors="coerce")
            cutoff = pd.Timestamp(reporting_date).normalize()
            week_start = cutoff - pd.Timedelta(days=cutoff.weekday())
            cumulative_mask = valid_case_mask & created.notna() & (created.dt.normalize() >= week_start) & (created.dt.normalize() <= cutoff)
        else:
            cumulative_mask = valid_case_mask
        wards = ward_map.loc[cumulative_mask, "ward"].dropna() if not ward_map.empty else pd.Series(dtype="string")
        ward_count = int(wards.nunique()) if not wards.empty else 0
    ward_coverage = None
    missing_wards = None
    benchmark_total = int(ward_master.get("listed_allocations")) if ward_master and ward_master.get("available") else total_wards
    if benchmark_total and benchmark_total > 0:
        ward_coverage = round(ward_count / benchmark_total * 100, 2)
        missing_wards = max(benchmark_total - ward_count, 0)
    status = _top_counts(df, cols["status"], 10)
    # Management status mapping: Active = still open; Resolved = closed; Cancelled = cancelled for other reasons.
    status_summary = _status_summary(df, cols["status"], valid_case_mask)
    created = pd.to_datetime(df[cols["created_on"]], errors="coerce") if cols.get("created_on") else pd.Series(pd.NaT, index=df.index)
    valid_all = created.notna() & valid_case_mask
    # Daily report channel mix is based on the manually selected reporting date.
    # Keep the full-history channel mix separately for downstream profiling.
    channel_all = _top_counts(df, cols["channel"], 15)
    target = pd.Timestamp(reporting_date).normalize() if reporting_date is not None else (created[valid_all].max().normalize() if valid_all.any() else None)
    selected_mask = valid_all & (created.dt.normalize() == target) if target is not None else valid_all
    selected_df = df.loc[selected_mask].copy()
    channel = _top_counts(selected_df, cols["channel"], 15)
    channel_new_wards = pd.DataFrame(columns=["value", "new_wards"])
    if cols["channel"] and target is not None and not selected_df.empty and not ward_map.empty:
        week_start = target - pd.Timedelta(days=target.weekday())
        prior_mask = valid_all & (created.dt.normalize() >= week_start) & (created.dt.normalize() < target)
        prior_wards = set(ward_map.loc[prior_mask, "ward"].dropna().astype(str))
        if ward_history is not None and not ward_history.empty:
            h = ward_history.copy()
            h["date"] = pd.to_datetime(h["date"], errors="coerce")
            prior_wards |= set(h.loc[(h["date"].dt.normalize() >= week_start) & (h["date"].dt.normalize() < target), "ward"].dropna().astype(str))
        selected_channel_wards = pd.DataFrame({
            "channel": df.loc[selected_mask, cols["channel"]].astype(str).values,
            "ward": ward_map.loc[selected_mask, "ward"].astype(str).values,
        })
        selected_channel_wards = selected_channel_wards[selected_channel_wards["ward"].notna() & (selected_channel_wards["ward"] != "nan")]
        if not selected_channel_wards.empty:
            selected_channel_wards["is_new"] = ~selected_channel_wards["ward"].isin(prior_wards)
            channel_new_wards = (selected_channel_wards[selected_channel_wards["is_new"]]
                                 .groupby("channel")["ward"].nunique()
                                 .rename("new_wards").reset_index()
                                 .rename(columns={"channel":"value"}))
    if not channel.empty:
        channel = channel.merge(channel_new_wards, on="value", how="left")
        channel["new_wards"] = channel["new_wards"].fillna(0).astype(int)
    cca_daily_tracker = _cca_daily_tracker(df, cols.get("created_on"), valid_case_mask, ward_map, reporting_date, ward_master, history=ward_history)
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
    if dates.get("available") and dates.get("peak_hour") is not None:
        insights.append({"id": "OPS-005", "type": "time_pattern", "finding": f"The highest case-creation hour in the selected reporting date is {dates['peak_hour']:02d}:00 with {dates['peak_hour_cases']:,} cases.", "evidence": "Created On grouped by hour for the selected reporting date."})

    corridor_coverage = pd.DataFrame()
    cca_coverage = pd.DataFrame()
    if ward_master and ward_master.get("available") and isinstance(dates.get("ward_coverage"), pd.DataFrame):
        # Slide 3 is a DAILY corridor-coverage view. A ward counts as covered in
        # a corridor only when it appears on the selected reporting date.
        wc_master = ward_master.get("master", pd.DataFrame()).copy()
        if not wc_master.empty and cols.get("created_on"):
            created = pd.to_datetime(df[cols["created_on"]], errors="coerce")
            day_mask = valid_case_mask & created.notna() & (created.dt.normalize() == pd.Timestamp(reporting_date).normalize())
            daily_wards_by_corridor = ward_map.loc[day_mask, ["ward","corridor"]].dropna().drop_duplicates()
            daily_set = set(daily_wards_by_corridor["ward"].astype(str))
            wc_day = wc_master.copy()
            wc_day["covered"] = wc_day["ward"].astype(str).isin(daily_set)
            corridor_coverage = wc_day.groupby("corridor", as_index=False).agg(target=("ward","count"))
            daily_unique = (daily_wards_by_corridor.groupby("corridor")["ward"].nunique().rename("covered"))
            corridor_coverage = corridor_coverage.merge(daily_unique, on="corridor", how="left")
            corridor_coverage["covered"] = corridor_coverage["covered"].fillna(0).astype(int)
            corridor_coverage["missing"] = (corridor_coverage["target"] - corridor_coverage["covered"]).clip(lower=0)
            corridor_coverage["coverage_pct"] = (corridor_coverage["covered"] / corridor_coverage["target"] * 100).round(2)
            cca_coverage = wc_day.groupby(["corridor","cca"], as_index=False).agg(target=("ward","count"))
            cca_unique = (daily_wards_by_corridor.merge(ward_map[["ward","corridor","cca"]].drop_duplicates(), on=["ward","corridor"], how="left")
                          .dropna(subset=["cca"]).groupby(["corridor","cca"])["ward"].nunique().rename("covered").reset_index())
            cca_coverage = cca_coverage.merge(cca_unique, on=["corridor","cca"], how="left")
            cca_coverage["covered"] = cca_coverage["covered"].fillna(0).astype(int)
            cca_coverage["missing"] = (cca_coverage["target"] - cca_coverage["covered"]).clip(lower=0)
            cca_coverage["coverage_pct"] = (cca_coverage["covered"] / cca_coverage["target"] * 100).round(2)
    ward_master_outside = int((ward_map["mapping_status"] == "Not in ward master").sum()) if not ward_map.empty else 0
    quality = _quality_findings(df, cols)
    return {
        "source_df": df.copy(),
        "reporting_date": reporting_date,
        "columns": cols,
        "summary": {
            "records": rows,
            "valid_cases": valid_cases,
            "invalid_case_records": rows - valid_cases,
            "distinct_wards": ward_count,
            "total_wards": benchmark_total,
            "ward_coverage_pct": ward_coverage,
            "missing_wards": missing_wards,
            "municipality": municipality,
            "ward_master_available": bool(ward_master and ward_master.get("available")),
            "ward_master_listed_allocations": int(ward_master.get("listed_allocations",0)) if ward_master else 0,
            "ward_master_unique_wards": int(ward_master.get("unique_wards",0)) if ward_master else 0,
            "ward_master_duplicate_wards": int(ward_master.get("duplicate_ward_numbers",0)) if ward_master else 0,
            "ward_master_outside_case_rows": ward_master_outside,
            "ward_master_outside_unique_wards": int(ward_map.loc[ward_map["mapping_status"] == "Not in ward master", "ward"].nunique()) if not ward_map.empty else 0,
            "retained_ward_history_days": int(pd.to_datetime(ward_history["date"], errors="coerce").dt.normalize().nunique()) if ward_history is not None and not ward_history.empty else 0,
            "ward_history_available": bool(ward_history is not None and not ward_history.empty),
        },
        "status": status,
        "status_summary": status_summary,
        "channel": channel,
        "channel_all": channel_all,
        "channel_new_wards": channel_new_wards,
        "cca_daily_tracker": cca_daily_tracker,
        "case_type": case_type,
        "priority": priority,
        "city": city,
        "category1": cat1,
        "category2": cat2,
        "category3": cat3,
        "owner": owner,
        "dates": dates,
        "ward_mapping": ward_map,
        "ward_master": ward_master or {"available": False},
        "corridor_coverage": corridor_coverage,
        "cca_coverage": cca_coverage,
        "quality": quality,
        "insights": pd.DataFrame(insights),
    }
