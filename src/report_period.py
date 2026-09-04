from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import calendar
import pandas as pd


PERIOD_TYPES = ["Daily", "Weekly", "Monthly", "Quarterly", "Year-to-Date", "Annual", "Custom"]


@dataclass(frozen=True)
class ReportingPeriod:
    period_type: str
    anchor_date: date
    start_date: date
    end_date: date
    label: str
    comparison_start: date | None = None
    comparison_end: date | None = None

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1


def _month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def resolve_reporting_period(
    period_type: str,
    anchor_date: date | datetime | pd.Timestamp,
    custom_start: date | datetime | pd.Timestamp | None = None,
    custom_end: date | datetime | pd.Timestamp | None = None,
) -> ReportingPeriod:
    """Resolve a user-selected reporting period without using upload timestamps."""
    anchor = pd.Timestamp(anchor_date).date()
    kind = str(period_type).strip().lower().replace("_", " ")
    kind = {
        "daily": "Daily", "weekly": "Weekly", "monthly": "Monthly",
        "quarterly": "Quarterly", "year-to-date": "Year-to-Date",
        "annual": "Annual", "custom": "Custom",
    }.get(kind, str(period_type).strip())

    if kind == "Daily":
        start = end = anchor
        label = anchor.strftime("%d %B %Y")
        comparison_start = comparison_end = anchor - pd.Timedelta(days=1)
    elif kind == "Weekly":
        # Reporting week follows the system's established Monday-Friday operating week.
        start = anchor - pd.Timedelta(days=anchor.weekday())
        end = start + pd.Timedelta(days=4)
        label = f"Week of {start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"
        comparison_start = start - pd.Timedelta(days=7)
        comparison_end = end - pd.Timedelta(days=7)
    elif kind == "Monthly":
        start = date(anchor.year, anchor.month, 1)
        end = _month_end(anchor.year, anchor.month)
        label = anchor.strftime("%B %Y")
        prev_month = pd.Timestamp(start) - pd.offsets.MonthBegin(1)
        comparison_start = prev_month.date()
        comparison_end = _month_end(prev_month.year, prev_month.month)
    elif kind == "Quarterly":
        q = (anchor.month - 1) // 3 + 1
        start_month = (q - 1) * 3 + 1
        start = date(anchor.year, start_month, 1)
        end = _month_end(anchor.year, start_month + 2)
        label = f"Q{q} {anchor.year}"
        comparison_start = pd.Timestamp(start) - pd.DateOffset(months=3)
        comparison_start = comparison_start.date()
        comparison_end = (pd.Timestamp(end) - pd.DateOffset(months=3)).date()
    elif kind == "Year-to-Date":
        start = date(anchor.year, 1, 1)
        end = anchor
        label = f"YTD {anchor.year} through {anchor.strftime('%d %b %Y')}"
        comparison_start = date(anchor.year - 1, 1, 1)
        comparison_end = (pd.Timestamp(anchor) - pd.DateOffset(years=1)).date()
    elif kind == "Annual":
        start = date(anchor.year, 1, 1)
        end = date(anchor.year, 12, 31)
        label = str(anchor.year)
        comparison_start = date(anchor.year - 1, 1, 1)
        comparison_end = date(anchor.year - 1, 12, 31)
    elif kind == "Custom":
        if custom_start is None or custom_end is None:
            raise ValueError("Custom reporting periods require both a start date and an end date.")
        start = pd.Timestamp(custom_start).date()
        end = pd.Timestamp(custom_end).date()
        if end < start:
            raise ValueError("Custom period end date cannot be earlier than its start date.")
        label = f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"
        length = (end - start).days + 1
        comparison_end = start - pd.Timedelta(days=1)
        comparison_start = comparison_end - pd.Timedelta(days=length - 1)
    else:
        raise ValueError(f"Unsupported reporting period: {period_type}")

    def as_date(v):
        return pd.Timestamp(v).date() if v is not None else None

    return ReportingPeriod(
        period_type=kind,
        anchor_date=anchor,
        start_date=as_date(start),
        end_date=as_date(end),
        label=label,
        comparison_start=as_date(comparison_start),
        comparison_end=as_date(comparison_end),
    )


def period_mask(
    values: pd.Series,
    period: ReportingPeriod,
    inclusive: str = "both",
) -> pd.Series:
    dt = pd.to_datetime(values, errors="coerce")
    return dt.dt.normalize().between(
        pd.Timestamp(period.start_date), pd.Timestamp(period.end_date), inclusive=inclusive
    )


def summarize_period(
    df: pd.DataFrame,
    date_column: str | None,
    period: ReportingPeriod,
    valid_mask: pd.Series | None = None,
) -> dict:
    """Return transparent period-level facts used by the reporting planner."""
    if not date_column or date_column not in df.columns:
        return {
            "available": False,
            "reason": "No usable reporting-date field was identified.",
            "period": period,
        }
    dates = pd.to_datetime(df[date_column], errors="coerce")
    if valid_mask is None:
        valid_mask = pd.Series(True, index=df.index)
    valid = valid_mask & dates.notna()
    current_mask = valid & period_mask(dates, period)
    comparison_mask = pd.Series(False, index=df.index)
    if period.comparison_start and period.comparison_end:
        comparison_mask = valid & dates.dt.normalize().between(
            pd.Timestamp(period.comparison_start), pd.Timestamp(period.comparison_end), inclusive="both"
        )
    current = dates[current_mask]
    comparison = dates[comparison_mask]
    current_count = int(current_mask.sum())
    comparison_count = int(comparison_mask.sum())
    change_pct = None if comparison_count == 0 else round((current_count - comparison_count) / comparison_count * 100, 2)
    return {
        "available": True,
        "period": period,
        "current_records": current_count,
        "comparison_records": comparison_count,
        "comparison_case_count": comparison_count,
        "change_pct": change_pct,
        "current_mask": current_mask,
        "comparison_mask": comparison_mask,
        "current_min": current.min() if not current.empty else None,
        "current_max": current.max() if not current.empty else None,
        "comparison_min": comparison.min() if not comparison.empty else None,
        "comparison_max": comparison.max() if not comparison.empty else None,
        "current_daily": dates[current_mask].dt.date.value_counts().sort_index().rename_axis("date").reset_index(name="cases"),
        "comparison_daily": dates[comparison_mask].dt.date.value_counts().sort_index().rename_axis("date").reset_index(name="cases"),
    }
