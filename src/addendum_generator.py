from __future__ import annotations
from pathlib import Path
from typing import Any
import pandas as pd


def _safe_sheet(name: str) -> str:
    bad = '[]:*?/\\'
    for ch in bad:
        name = name.replace(ch, '_')
    return name[:31]


def _write_df(writer, df: pd.DataFrame, sheet: str):
    if df is None or df.empty:
        pd.DataFrame({"Note": ["No records available for this section."]}).to_excel(writer, sheet_name=_safe_sheet(sheet), index=False)
    else:
        df.to_excel(writer, sheet_name=_safe_sheet(sheet), index=False)


def generate_addendum(output_path: str | Path, source_filename: str, sheet_name: str, analysis: dict[str, Any], intelligence: dict[str, Any], municipality: str, reporting_date, period_covered: str, close_time: str) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary = analysis["summary"]
    context = pd.DataFrame([
        ["Report", "OOP Corridor Daily Operations Report"], ["Municipality / corridor", municipality],
        ["Reporting date", reporting_date.isoformat()], ["Period covered", period_covered or "Not specified"],
        ["Data close time", close_time], ["Source file", source_filename], ["Source sheet", sheet_name],
        ["Records analysed", summary["records"]], ["Valid cases", summary["valid_cases"]],
        ["Configured total wards", summary["total_wards"] if summary["total_wards"] is not None else "Not configured"],
        ["Distinct wards represented", summary["distinct_wards"]],
        ["Represented ward coverage %", summary["ward_coverage_pct"] if summary["ward_coverage_pct"] is not None else "Not configured"],
        ["Missing/unrepresented wards", summary["missing_wards"] if summary["missing_wards"] is not None else "Not configured"],
    ], columns=["Item", "Value"])
    dictionary = pd.DataFrame([{"field_role": k, "source_column": v, "usable": bool(v)} for k, v in analysis["columns"].items()])
    calculations = pd.DataFrame([
        {"metric":"Records analysed","value":summary["records"],"calculation":"Number of rows in selected sheet"},
        {"metric":"Valid cases","value":summary["valid_cases"],"calculation":"Records with a non-empty mapped Case Number"},
        {"metric":"Invalid case records","value":summary["invalid_case_records"],"calculation":"Records analysed - valid cases"},
        {"metric":"Distinct wards represented","value":summary["distinct_wards"],"calculation":"Unique non-empty values in mapped Ward field"},
        {"metric":"Ward coverage %","value":summary["ward_coverage_pct"],"calculation":"Distinct wards represented / configured total wards × 100"},
        {"metric":"Missing/unrepresented wards","value":summary["missing_wards"],"calculation":"Configured total wards - distinct wards represented"},
    ])
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        context.to_excel(writer, sheet_name="Report Context", index=False)
        calculations.to_excel(writer, sheet_name="Calculations", index=False)
        dictionary.to_excel(writer, sheet_name="Data Dictionary", index=False)
        _write_df(writer, analysis.get("quality"), "Data Quality")
        for key, sheet in [("status","Status"),("channel","Channel"),("case_type","Case Type"),("priority","Priority"),("city","City Area"),("category1","Demand Cat 1"),("category2","Demand Cat 2"),("category3","Demand Cat 3"),("owner","Owner")]:
            _write_df(writer, analysis.get(key), sheet)
        dates = analysis.get("dates", {})
        _write_df(writer, dates.get("by_date") if dates.get("available") else None, "Cases by Date")
        _write_df(writer, dates.get("by_hour") if dates.get("available") else None, "Cases by Hour")
        _write_df(writer, intelligence.get("findings"), "Findings")
        _write_df(writer, intelligence.get("recommendations"), "Recommendations")
        _write_df(writer, intelligence.get("evidence"), "Evidence Register")
        _write_df(writer, intelligence.get("evidence_details"), "Evidence Detail")
        _write_df(writer, intelligence.get("qa"), "Traceability QA")
        _write_df(writer, intelligence.get("final_report_qa"), "Final Report QA")
        ward_note = pd.DataFrame({"Item":["Ward representation is based on distinct non-empty Ward Id values."],"Configured total wards":[summary["total_wards"]],"Distinct wards represented":[summary["distinct_wards"]],"Coverage %":[summary["ward_coverage_pct"]],"Missing/unrepresented":[summary["missing_wards"]]})
        ward_note.to_excel(writer, sheet_name="Ward Coverage", index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for col_cells in ws.columns:
                max_len = 0
                for cell in list(col_cells)[:200]:
                    val = "" if cell.value is None else str(cell.value)
                    max_len = max(max_len, len(val))
                ws.column_dimensions[col_cells[0].column_letter].width = min(max(max_len + 2, 10), 45)
    return output_path
