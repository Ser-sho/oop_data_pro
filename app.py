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
from ppt_generator import generate_powerpoint
from addendum_generator import generate_addendum
from template_intelligence import assess_template
from audience_engine import build_audience_view
from qa_engine import run_report_qa, qa_status

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
    audience = st.selectbox("Report audience", ["Executive management", "Operations management", "Analyst", "Custom"])
    report_requirements = st.text_area("Reporting requirements (optional)", placeholder="e.g. Focus on ward coverage, service demand, unresolved cases and actions.")
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
audience_view = build_audience_view(intelligence, audience, report_requirements)

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

st.subheader(f"Management findings — {audience}")
if audience_view["findings"].empty:
    st.info("No management findings were produced.")
else:
    st.dataframe(audience_view["findings"], use_container_width=True, hide_index=True)

st.subheader(f"Recommendations — {audience}")
if audience_view["recommendations"].empty:
    st.info("No additional recommendations were triggered by the current rules.")
else:
    st.dataframe(audience_view["recommendations"], use_container_width=True, hide_index=True)

st.subheader("Audience configuration")
st.write({"audience": audience, "detail_level": audience_view["guidance"]["detail"], "tone": audience_view["guidance"]["tone"], "focus": audience_view["guidance"]["focus"], "max_findings": audience_view["guidance"]["max_findings"], "max_recommendations": audience_view["guidance"]["max_recommendations"]})

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

st.divider()
st.divider()
st.subheader("Template intelligence")
template_default = ROOT.parent / "Generic Corridor Operations Report Template V1.pptx"
template_upload = st.file_uploader("Optional: upload/replace the PowerPoint template", type=["pptx"], key="ppt_template")
if template_upload is not None:
    template_path = ROOT / "_uploaded_template.pptx"
    template_path.write_bytes(template_upload.getbuffer())
elif template_default.exists():
    template_path = template_default
else:
    template_path = None

if template_path is not None:
    template_assessment = assess_template(template_path, analysis, report_requirements)
    st.metric("Template coverage", f"{template_assessment['score']:.1f}%")
    st.dataframe(pd.DataFrame(template_assessment["sections"]), use_container_width=True, hide_index=True)
    if report_requirements.strip():
        st.subheader("Requirement coverage")
        st.dataframe(pd.DataFrame(template_assessment["requirements"]), use_container_width=True, hide_index=True)
    if template_assessment["recommendations"]:
        st.subheader("Template recommendations")
        for rec in template_assessment["recommendations"]:
            st.warning(rec)


st.subheader("Final Report QA")
qa_template_assessment = locals().get("template_assessment", None)
final_qa = run_report_qa(
    analysis,
    intelligence,
    audience_view,
    template_assessment=qa_template_assessment,
    report_requirements=report_requirements,
)
status = qa_status(final_qa)
if status == "READY FOR REVIEW":
    st.success("🟢 READY FOR REVIEW — all blocking QA checks passed.")
elif status == "REVIEW REQUIRED":
    st.warning("🟠 REVIEW REQUIRED — warnings must be reviewed before circulation.")
else:
    st.error("🔴 REPORT BLOCKED — one or more critical QA checks failed.")
st.dataframe(final_qa, use_container_width=True, hide_index=True)

st.subheader("Generate PowerPoint report")
if template_path is None:
    st.info("Place the Generic Corridor Operations Report Template V1.pptx in the project folder or upload it above.")
elif st.button("Generate OOP Corridor PowerPoint", type="primary"):
    if status == "REPORT BLOCKED":
        st.error("PowerPoint generation is blocked until critical QA failures are resolved.")
    else:
        out_dir = ROOT / "outputs"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"OOP_Corridor_Daily_Operations_Report_{reporting_date.strftime('%Y%m%d')}.pptx"
        try:
            generate_powerpoint(template_path, out_path, analysis, intelligence, municipality, reporting_date, period_covered, close_time.strftime("%H:%M"), audience_view=audience_view)
            st.success("PowerPoint report generated successfully.")
            st.download_button("Download PowerPoint report", data=out_path.read_bytes(), file_name=out_path.name, mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
        except Exception as exc:
            st.error(f"Could not generate the PowerPoint: {exc}")

st.divider()
st.subheader("Generate analytical addendum")
st.write("The Excel addendum keeps detailed evidence, calculations, distributions and QA outside the PowerPoint so the management report stays concise.")
if st.button("Generate Excel Analytical Addendum"):
    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    add_path = out_dir / f"OOP_Corridor_Daily_Operations_Addendum_{reporting_date.strftime('%Y%m%d')}.xlsx"
    try:
        intelligence_with_qa = dict(intelligence)
        intelligence_with_qa["final_report_qa"] = final_qa
        generate_addendum(add_path, uploaded.name, sheet_name, analysis, intelligence_with_qa, municipality, reporting_date, period_covered, close_time.strftime("%H:%M"))
        st.success("Excel analytical addendum generated successfully.")
        st.download_button("Download Excel addendum", data=add_path.read_bytes(), file_name=add_path.name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as exc:
        st.error(f"Could not generate the addendum: {exc}")

st.caption("V1 analysis is deliberately transparent: calculations are deterministic; PowerPoint generation is template-driven; the Excel addendum provides the supporting evidence layer.")
