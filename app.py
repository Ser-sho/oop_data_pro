from __future__ import annotations

from datetime import date, time
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
from data_profiler import profile_dataframe
from analysis_engine import analyze_operations
from intelligence_engine import build_intelligence

st.set_page_config(page_title="OOP Corridor Daily Operations Report", layout="wide")
st.title("OOP Corridor Daily Operations Report")
st.caption("V1 — Data foundation + corridor operations analysis")

with st.sidebar:
    st.header("Report controls")
    municipality = st.text_input("Municipality / corridor", value="Ekurhuleni")
    total_wards = st.number_input("Total wards (optional)", min_value=0, value=0, step=1, help="Enter the official total for the municipality. This is never inferred from the dataset.")
    reporting_date = st.date_input("Reporting date", value=date.today())
    period_covered = st.text_input("Period covered", placeholder="e.g. Friday 21 Aug 2026")
    close_time = st.time_input("Data close time", value=time(17, 0))
    st.info("Reporting date and close time are manual. They are never inferred from the latest data timestamp.")

uploaded = st.file_uploader("Upload the operations dataset", type=["xlsx", "xls", "csv"])
if uploaded is None:
    st.markdown("### Start here")
    st.write("Upload the SERSHO workbook or another corridor operations dataset.")
    st.stop()

try:
    if uploaded.name.lower().endswith(".csv"):
        sheets = {"CSV": pd.read_csv(uploaded, low_memory=False)}
    else:
        workbook = pd.ExcelFile(uploaded)
        sheets = {name: pd.read_excel(uploaded, sheet_name=name) for name in workbook.sheet_names}
except Exception as exc:
    st.error(f"Could not read the file: {exc}")
    st.stop()

st.success(f"Loaded {uploaded.name}")
sheet_name = st.selectbox("Sheet to analyse", list(sheets.keys()), index=0)
df = sheets[sheet_name]

profile = profile_dataframe(df)
analysis = analyze_operations(df, total_wards=int(total_wards) if total_wards else None, municipality=municipality)
intelligence = build_intelligence(analysis, total_wards=int(total_wards) if total_wards else None)

st.subheader("Report context")
st.write({"municipality": municipality, "reporting_date": reporting_date.isoformat(), "period_covered": period_covered or "Not specified", "data_close_time": close_time.strftime("%H:%M")})

st.subheader("Operational overview")
metrics = [
    ("Records", analysis["summary"]["records"]),
    ("Valid cases", analysis["summary"]["valid_cases"]),
    ("Distinct wards represented", analysis["summary"]["distinct_wards"]),
    ("Ward coverage", f"{analysis['summary']['ward_coverage_pct']:.1f}%" if analysis["summary"]["ward_coverage_pct"] is not None else "Not configured"),
    ("Missing wards", analysis["summary"]["missing_wards"] if analysis["summary"]["missing_wards"] is not None else "Not configured"),
    ("Quality findings", len(analysis["quality"])),
]
cols = st.columns(6)
for col, (label, value) in zip(cols, metrics):
    col.metric(label, f"{value:,}" if isinstance(value, int) else value)

st.subheader("Key analytical findings")
if analysis["insights"].empty:
    st.info("No automated findings were produced from the available mapped fields.")
else:
    st.dataframe(analysis["insights"], use_container_width=True, hide_index=True)

left, right = st.columns(2)
with left:
    st.subheader("Status")
    st.dataframe(analysis["status"], use_container_width=True, hide_index=True)
    st.subheader("Case type")
    st.dataframe(analysis["case_type"], use_container_width=True, hide_index=True)
    st.subheader("Service / demand — Category 1")
    st.dataframe(analysis["category1"], use_container_width=True, hide_index=True)
with right:
    st.subheader("Channel")
    st.dataframe(analysis["channel"], use_container_width=True, hide_index=True)
    st.subheader("Priority")
    st.dataframe(analysis["priority"], use_container_width=True, hide_index=True)
    st.subheader("City / area")
    st.dataframe(analysis["city"], use_container_width=True, hide_index=True)

st.subheader("Time analysis")
if analysis["dates"].get("available"):
    d = analysis["dates"]
    st.write(f"Available Created On range: **{d['min']}** to **{d['max']}**. Peak creation hour: **{d['peak_hour']:02d}:00** ({d['peak_hour_cases']:,} cases).")
    st.dataframe(d["by_hour"], use_container_width=True, hide_index=True)
else:
    st.info("No usable Created On timestamps were found.")

st.subheader("Management findings")
if intelligence["findings"].empty:
    st.info("No management findings were produced.")
else:
    st.dataframe(intelligence["findings"], use_container_width=True, hide_index=True)

st.subheader("Recommendations")
if intelligence["recommendations"].empty:
    st.info("No additional recommendations were triggered by the current rules.")
else:
    st.dataframe(intelligence["recommendations"], use_container_width=True, hide_index=True)

st.subheader("Evidence register")
st.dataframe(intelligence["evidence"], use_container_width=True, hide_index=True)

st.subheader("Intelligence QA")
qa_pass = intelligence["qa"]["status"].eq("PASS").all() if not intelligence["qa"].empty else True
if qa_pass:
    st.success("All generated findings and recommendations have valid evidence references.")
else:
    st.error("One or more intelligence items failed evidence-reference QA.")
st.dataframe(intelligence["qa"], use_container_width=True, hide_index=True)

st.subheader("Data-quality findings")
if analysis["quality"].empty:
    st.success("No mapped operational quality issues detected.")
else:
    st.dataframe(analysis["quality"], use_container_width=True, hide_index=True)

with st.expander("Data dictionary / mapped fields"):
    st.json(analysis["columns"])

with st.expander("Full dataset sample"):
    st.dataframe(df.head(50), use_container_width=True, hide_index=True)

st.caption("V1 analysis is deliberately transparent: calculations are deterministic; AI narrative, recommendations, PowerPoint generation and the analytical addendum are the next build stages.")
