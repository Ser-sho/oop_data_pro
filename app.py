from __future__ import annotations

from datetime import date, time, timedelta
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
from data_profiler import profile_dataframe
from analysis_engine import analyze_operations, parse_ward_master_excel
from intelligence_engine import build_intelligence
from ppt_generator import generate_powerpoint
from addendum_generator import generate_addendum
from template_intelligence import assess_template
from audience_engine import build_audience_view
from qa_engine import run_report_qa, qa_status
from voc_engine import analyze_voc
from report_period import PERIOD_TYPES, resolve_reporting_period, summarize_period
from report_planner import build_report_plan, plan_dataframe

st.set_page_config(page_title="OOP Corridor Daily Operations Report", layout="wide")
st.title("Dynamic Operations & Analytics Reporting System")
st.caption("V3.1 — Data foundation + reporting-period framework + dynamic report planner")

with st.sidebar:
    st.header("Report controls")
    department = st.text_input("Department / entity", value="Ekurhuleni", help="The department or entity being reported on, e.g. SASSA, Home Affairs, Health or Education.")
    requesting_team = st.text_input("Requesting internal team", value="Operations Team", help="The internal team requesting the report, e.g. Operations Team, Entity Team or Management.")
    municipality = st.text_input("Municipality / corridor / reporting scope", value="Ekurhuleni")
    total_wards = st.number_input("Total wards (optional)", min_value=0, value=0, step=1, help="Enter the official total for the municipality. This is never inferred from the dataset.")
    reporting_date = st.date_input("Anchor / reporting date", value=date.today())
    period_type = st.selectbox("Reporting period", PERIOD_TYPES, index=0, help="The period is explicitly selected. It is never inferred from the latest uploaded timestamp.")
    custom_start = custom_end = None
    if period_type == "Custom":
        custom_start = st.date_input("Custom period start", value=reporting_date)
        custom_end = st.date_input("Custom period end", value=reporting_date)
    period_covered = st.text_input("Period covered (optional display text)", placeholder="e.g. Q3 2026 or Friday 21 Aug 2026")
    close_time = st.time_input("Data close time", value=time(17, 0))
    audience = st.selectbox("Report audience", ["Executive management", "Operations management", "Analyst", "Custom"])
    report_requirements = st.text_area("Reporting requirements (optional)", placeholder="e.g. Focus on ward coverage, service demand, unresolved cases and actions.")
    ward_master_uploaded = st.file_uploader("Ward master / CCA allocation (optional)", type=["xlsx", "xls"], key="ward_master")
    st.info("Reporting date and close time are manual. They are never inferred from the latest data timestamp.")
    st.caption("Ward history is kept separately by municipality/corridor and reporting week. Reporting date controls the week; upload date does not.")
    if st.button("Clear retained ward history"):
        st.session_state["ward_history_by_scope"] = {}
        st.rerun()

uploaded = st.file_uploader("Upload the operations dataset", type=["xlsx", "xls", "csv"])
voc_uploaded = st.file_uploader("Upload VOC dataset (optional)", type=["xlsx", "xls", "csv"], key="voc_dataset")
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
ward_master = {"available": False}
ward_master_name = "Not supplied"
ward_master_source = ward_master_uploaded
if ward_master_source is None:
    default_master = ROOT / "EMM CCC & Wards.xlsx"
    if default_master.exists() and municipality.strip().lower() == "ekurhuleni":
        ward_master_source = default_master
if ward_master_source is not None:
    try:
        ward_master = parse_ward_master_excel(ward_master_source)
        ward_master_name = getattr(ward_master_source, "name", Path(str(ward_master_source)).name)
        if ward_master.get("available"):
            total_wards = ward_master["listed_allocations"]
            st.sidebar.success(f"Ward master loaded: {total_wards} listed allocations / {ward_master['unique_wards']} unique ward numbers")
            if ward_master.get("unique_wards") != ward_master.get("listed_allocations"):
                st.sidebar.warning("Ward master contains duplicate ward allocations. These are preserved and flagged; they are not silently removed.")
    except Exception as exc:
        st.sidebar.error(f"Could not read ward master: {exc}")
# Retain only compact ward/date evidence across separate uploads in this session.
# History is scoped by BOTH municipality/corridor and reporting week.
# Raw case data is never copied into the history store.
if "ward_history_by_scope" not in st.session_state:
    st.session_state["ward_history_by_scope"] = {}
if "ward_history_by_municipality" in st.session_state:
    # Upgrade older V2.5 session state without mixing its records across weeks.
    legacy = st.session_state.pop("ward_history_by_municipality")
    st.session_state["ward_history_by_scope"].update({str(k): v for k, v in legacy.items()})

reporting_target = pd.Timestamp(reporting_date).normalize()
try:
    reporting_period = resolve_reporting_period(period_type, reporting_date, custom_start, custom_end)
except ValueError as exc:
    st.error(str(exc))
    st.stop()
week_start = reporting_target - pd.Timedelta(days=reporting_target.weekday())
history_key = f"{municipality.strip().lower() or 'default'}|week:{week_start.date()}"
ward_history = st.session_state["ward_history_by_scope"].get(
    history_key, pd.DataFrame(columns=["date","ward","corridor","cca","daily_cases"])
)
analysis = analyze_operations(
    df,
    total_wards=int(total_wards) if total_wards else None,
    municipality=municipality,
    reporting_date=reporting_date,
    ward_master=ward_master,
    ward_history=ward_history,
)

period_summary = summarize_period(
    df,
    analysis.get("columns", {}).get("created_on"),
    reporting_period,
    valid_mask=(pd.Series(True, index=df.index) if not analysis.get("columns", {}).get("case_id") else df[analysis["columns"]["case_id"]].notna()),
)

# Add the current upload's mapped ward/date evidence to retained session history.
# Case-level duplicates do not matter because history is deduplicated to date/ward/CCA.
if ward_master.get("available") and analysis.get("ward_mapping") is not None:
    created_col = analysis["columns"].get("created_on")
    if created_col and created_col in df.columns:
        current_dates = pd.to_datetime(df[created_col], errors="coerce").dt.normalize()
        # Only retain evidence that belongs to the selected reporting week and is
        # not later than the manually selected reporting date. This prevents a
        # Friday upload from contaminating a Monday report, for example.
        in_scope = current_dates.notna() & (current_dates >= week_start) & (current_dates <= reporting_target)
        daily_case_counts = current_dates[in_scope].value_counts(dropna=True).to_dict()
        current_hist = pd.DataFrame({
            "date": current_dates,
            "daily_cases": current_dates.map(daily_case_counts),
            "ward": analysis["ward_mapping"]["ward"],
            "corridor": analysis["ward_mapping"]["corridor"],
            "cca": analysis["ward_mapping"]["cca"],
        })
        current_hist = current_hist.loc[in_scope].dropna(subset=["date","ward","corridor","cca"])
        current_hist = current_hist.drop_duplicates(subset=["date","ward","corridor","cca"])
        if not current_hist.empty:
            # A later upload for the same reporting date is treated as a correction
            # or replacement for that date, rather than being unioned with stale wards.
            existing = ward_history.copy()
            if "daily_cases" not in existing.columns:
                existing["daily_cases"] = pd.NA
            replace_dates = set(pd.to_datetime(current_hist["date"]).dt.normalize())
            if not existing.empty:
                existing["date"] = pd.to_datetime(existing["date"], errors="coerce").dt.normalize()
                existing = existing[~existing["date"].isin(replace_dates)]
            combined_hist = pd.concat([existing, current_hist], ignore_index=True)
            combined_hist["date"] = pd.to_datetime(combined_hist["date"], errors="coerce").dt.normalize()
            combined_hist = combined_hist.dropna(subset=["date","ward","corridor","cca"]).drop_duplicates(subset=["date","ward","corridor","cca"]).sort_values(["date","corridor","cca","ward"]).reset_index(drop=True)
            st.session_state["ward_history_by_scope"][history_key] = combined_hist

voc_df = None
if voc_uploaded is not None:
    try:
        if voc_uploaded.name.lower().endswith(".csv"):
            voc_df = pd.read_csv(voc_uploaded, low_memory=False)
        else:
            vx = pd.ExcelFile(voc_uploaded)
            voc_df = pd.read_excel(voc_uploaded, sheet_name=vx.sheet_names[0])
        st.success(f"Loaded VOC dataset: {voc_uploaded.name}")
    except Exception as exc:
        st.error(f"Could not read the VOC file: {exc}")
voc_analysis = analyze_voc(voc_df)
intelligence = build_intelligence(analysis, total_wards=int(total_wards) if total_wards else None)
audience_view = build_audience_view(intelligence, audience, report_requirements)
report_plan = build_report_plan(analysis, department, requesting_team, reporting_period, report_requirements, audience, voc_analysis)

st.subheader("Dynamic report planner")
st.write({"department": department, "requesting_team": requesting_team, "reporting_period": reporting_period.label, "audience": audience})
st.caption("The planner determines what the report should contain from the department, requesting team, selected period, available data and user focus. It does not require a supplied PowerPoint template.")
plan_status = "READY TO DESIGN" if not report_plan["gaps"] else "READY WITH FOCUS GAPS"
if plan_status == "READY TO DESIGN":
    st.success("🟢 Report plan is ready for the automatic report designer.")
else:
    st.warning("🟠 The report can be planned, but one or more requested focus areas are not supported by the supplied data.")
st.dataframe(plan_dataframe(report_plan), use_container_width=True, hide_index=True)
if report_plan["gaps"]:
    st.subheader("Planner focus gaps")
    st.dataframe(pd.DataFrame(report_plan["gaps"]), use_container_width=True, hide_index=True)
with st.expander("Report design rules"):
    st.write(report_plan["design_requirements"])
    st.write({"main_report": report_plan["main_report_rule"], "addendum": report_plan["addendum_rule"]})

st.subheader("Report context")
st.write({
    "municipality": municipality,
    "period_type": reporting_period.period_type,
    "period": reporting_period.label,
    "period_start": reporting_period.start_date.isoformat(),
    "period_end": reporting_period.end_date.isoformat(),
    "comparison_period_start": reporting_period.comparison_start.isoformat() if reporting_period.comparison_start else None,
    "comparison_period_end": reporting_period.comparison_end.isoformat() if reporting_period.comparison_end else None,
    "anchor_date": reporting_period.anchor_date.isoformat(),
    "period_covered_display": period_covered or "Not specified",
    "data_close_time": close_time.strftime("%H:%M"),
})

st.subheader("Reporting-period intelligence")
if period_summary.get("available"):
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Period", reporting_period.label)
    p2.metric("Period cases", f"{period_summary['current_records']:,}")
    p3.metric("Comparison cases", f"{period_summary['comparison_records']:,}")
    if period_summary['comparison_records']:
        change = (period_summary['current_records'] - period_summary['comparison_records']) / period_summary['comparison_records'] * 100
        p4.metric("Cases vs comparison", f"{change:+.1f}%")
    else:
        p4.metric("Cases vs comparison", "No baseline")
    if reporting_period.period_type != "Daily":
        st.info("The reporting-period framework is active. The current Operations analysis engine remains daily/template-specific; multi-period report planning is the next integration layer. No daily metric is being mislabeled as a quarterly/monthly result.")
else:
    st.warning(period_summary.get("reason", "Reporting period could not be evaluated."))


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

if analysis["dates"].get("available"):
    st.subheader("Daily vs cumulative ward coverage")
    sd = analysis["dates"].get("selected_day", {})
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Cases today", f"{int(sd.get('cases', 0)):,}")
    m2.metric("Daily wards", f"{int(sd.get('daily_wards', 0)):,}")
    m3.metric("New wards", f"{int(sd.get('new_wards', 0)):,}")
    m4.metric("Running wards", f"{int(sd.get('running_wards', 0)):,}")
    m5.metric("Still needed", f"{int(sd.get('still_needed', 0)):,}" if sd.get('still_needed') is not None else "Not configured")
    if sd.get("ward_history_status"):
        if str(sd["ward_history_status"]).startswith("Baseline"):
            st.info(f"Ward history status: {sd['ward_history_status']}. New wards on this first supplied day are a baseline, not a claim about days outside the supplied history.")
        else:
            st.success(f"Ward history status: {sd['ward_history_status']}.")
    pace = sd.get("suggested_new_wards_per_remaining_day")
    rem_days = sd.get("remaining_workdays_in_week")
    if pace is not None and rem_days is not None and rem_days > 0:
        st.caption(f"Target pace: {pace} new wards per remaining working day to reach {analysis['summary'].get('total_wards') or 0} wards by Friday ({rem_days} working day(s) remaining).")
    tracker = analysis["dates"].get("daily_tracker")
    if isinstance(tracker, pd.DataFrame) and not tracker.empty:
        st.dataframe(tracker, use_container_width=True, hide_index=True)
    if analysis.get("ward_master", {}).get("available"):
        st.caption(f"Ward master: {ward_master_name}. Coverage benchmark is the supplied allocation register, not the number of wards observed in the raw data.")
        if analysis["summary"].get("ward_master_duplicate_wards", 0) or analysis["summary"].get("ward_master_outside_unique_wards", 0):
            st.warning(f"Ward-master validation: {analysis['summary'].get('ward_master_duplicate_wards',0)} duplicate allocation rows and {analysis['summary'].get('ward_master_outside_unique_wards',0)} observed unique ward number(s) outside the supplied master. These are flagged, not silently corrected.")

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
template_default = ROOT / "Generic Corridor Operations Report Template V1.pptx"
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
elif reporting_period.period_type != "Daily":
    st.info("PowerPoint generation is currently limited to the existing daily Operations template. The selected multi-day period is calculated and validated above; the dynamic multi-period report builder will use the new period framework rather than forcing a daily template onto a quarterly/monthly report.")
elif st.button("Generate OOP Corridor PowerPoint", type="primary"):
    if status == "REPORT BLOCKED":
        st.error("PowerPoint generation is blocked until critical QA failures are resolved.")
    else:
        out_dir = ROOT / "outputs"
        out_dir.mkdir(exist_ok=True)
        base = out_dir / f"OOP_Corridor_Daily_Operations_Report_{reporting_date.strftime('%Y%m%d')}"
        out_path = base.with_suffix('.pptx')
        n = 2
        while out_path.exists():
            out_path = out_dir / f"{base.name}_v{n}.pptx"
            n += 1
        try:
            generate_powerpoint(template_path, out_path, analysis, intelligence, municipality, reporting_date, period_covered, close_time.strftime("%H:%M"), audience_view=audience_view, voc_analysis=voc_analysis)
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
    base = out_dir / f"OOP_Corridor_Daily_Operations_Addendum_{reporting_date.strftime('%Y%m%d')}"
    add_path = base.with_suffix('.xlsx')
    n = 2
    while add_path.exists():
        add_path = out_dir / f"{base.name}_v{n}.xlsx"
        n += 1
    try:
        intelligence_with_qa = dict(intelligence)
        intelligence_with_qa["final_report_qa"] = final_qa
        generate_addendum(add_path, uploaded.name, sheet_name, analysis, intelligence_with_qa, municipality, reporting_date, period_covered, close_time.strftime("%H:%M"), voc_analysis=voc_analysis)
        st.success("Excel analytical addendum generated successfully.")
        st.download_button("Download Excel addendum", data=add_path.read_bytes(), file_name=add_path.name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as exc:
        st.error(f"Could not generate the addendum: {exc}")

st.caption("V1 analysis is deliberately transparent: calculations are deterministic; PowerPoint generation is template-driven; the Excel addendum provides the supporting evidence layer.")
