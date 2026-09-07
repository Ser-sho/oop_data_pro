from __future__ import annotations
import pandas as pd


def analyze_voc(df: pd.DataFrame | None) -> dict:
    if df is None or df.empty:
        return {"available": False, "responses": 0}
    cols = list(df.columns)
    submit = next((c for c in cols if str(c).strip().lower().startswith("submit date")), None)
    resolution = next((c for c in cols if "happy with how" in str(c).lower() and "resolved" in str(c).lower()), None)
    satisfaction = next((c for c in cols if "how satisfied" in str(c).lower()), None)
    ease = next((c for c in cols if "how easy" in str(c).lower()), None)
    promote = next((c for c in cols if "how likely" in str(c).lower() and "promote" in str(c).lower()), None)
    out = {"available": True, "responses": len(df), "date_column": submit, "columns": {"resolution": resolution, "satisfaction": satisfaction, "ease": ease, "promote": promote}}
    if resolution:
        x=df[resolution].astype("string").str.strip().str.lower()
        out["happiness"] = f"{(x.eq('yes').mean()*100):.1f}%" if len(x) else "Not calculated"
        out["resolved"] = int(x.eq("yes").sum())
    else:
        out["happiness"]="Not calculated"; out["resolved"]="Not calculated"
    required=[c for c in [resolution,satisfaction,ease,promote] if c]
    if required:
        ready=df[required].notna().all(axis=1).sum()
        out["survey_ready"] = f"{ready}/{len(df)}"
    else:
        out["survey_ready"]="Not calculated"
    if submit:
        dt=pd.to_datetime(df[submit], errors="coerce")
        out["min_date"] = dt.min(); out["max_date"] = dt.max()
    return out
