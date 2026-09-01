from __future__ import annotations
from pathlib import Path
import math
import re
import pandas as pd
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.dml.color import RGBColor
from pptx.util import Pt

# Template-faithful renderer: it edits existing template shapes instead of drawing
# a new presentation on top of the design.


def _shape_text(shape) -> str:
    return getattr(shape, "text", "") if hasattr(shape, "text") else ""


def _set_text_preserve_style(shape, text: str):
    if not hasattr(shape, "text_frame"):
        return
    tf = shape.text_frame
    if not tf.paragraphs:
        tf.text = str(text)
        return
    p = tf.paragraphs[0]
    if p.runs:
        p.runs[0].text = str(text)
        for r in p.runs[1:]:
            r.text = ""
        # Remove extra paragraphs without rebuilding the shape.
        for extra in list(tf.paragraphs[1:]):
            p_el = extra._element
            p_el.getparent().remove(p_el)
    else:
        r = p.add_run()
        r.text = str(text)


def _replace_exact(slide, old: str, new: str):
    for shape in slide.shapes:
        if _shape_text(shape).strip() == old:
            _set_text_preserve_style(shape, new)
            return True
    return False


def _replace_all_tokens(slide, replacements):
    for shape in slide.shapes:
        if not hasattr(shape, "text_frame"):
            continue
        original = shape.text
        new = original
        for old, value in replacements.items():
            new = new.replace(old, str(value))
        if new != original:
            _set_text_preserve_style(shape, new)


def _set_fill(shape, rgb: str):
    try:
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(rgb)
    except Exception:
        pass


def _set_text_color(shape, rgb: str = "FFFFFF"):
    try:
        for p in shape.text_frame.paragraphs:
            for r in p.runs:
                r.font.color.rgb = RGBColor.from_string(rgb)
    except Exception:
        pass


def _rag_shape(slide, status: str):
    for shape in slide.shapes:
        if _shape_text(shape).strip() == "[RAG]":
            return shape
    return None


def _set_rag(slide, status: str):
    shape = _rag_shape(slide, status)
    if shape is None:
        return
    _set_text_preserve_style(shape, status)
    # RAG must be a real fill, not a word written onto the template's yellow box.
    fills = {"GREEN": "00A651", "AMBER": "FFC000", "RED": "C00000"}
    _set_fill(shape, fills.get(status, "FFC000"))
    _set_text_color(shape, "FFFFFF")


def _bar_shapes(slide, ids):
    out = []
    for i in ids:
        if i < len(slide.shapes):
            sh = slide.shapes[i]
            if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and sh.width > 0 and sh.height > 0:
                out.append(sh)
    return out


def _style_rgb(shape):
    try:
        return shape.fill.fore_color.rgb
    except Exception:
        return None


def _render_existing_bars(slide, ids, values, horizontal=False, max_value=None):
    bars = _bar_shapes(slide, ids)
    if not bars:
        return
    vals = [max(float(v), 0) for v in values[:len(bars)]]
    if not vals:
        vals = [0]
    scale_max = max_value if max_value is not None else max(vals) or 1
    # Keep the template's original bar colour and geometry; only resize/position.
    if horizontal:
        left = min(b.left for b in bars)
        for sh, val in zip(bars, vals):
            max_w = sh.width
            sh.width = int(max_w * (val / scale_max)) if scale_max else 0
            sh.left = left
    else:
        bottom = max(sh.top + sh.height for sh in bars)
        for sh, val in zip(bars, vals):
            max_h = sh.height
            new_h = int(max_h * (val / scale_max)) if scale_max else 0
            sh.top = bottom - new_h
            sh.height = max(new_h, 1)


def _table_value_shapes(slide, y_targets, x_targets):
    result = {}
    for sh in slide.shapes:
        if not hasattr(sh, "text"):
            continue
        y = round(sh.top / 914400, 2)
        x = round(sh.left / 914400, 2)
        if y in y_targets and x in x_targets:
            result[(y, x)] = sh
    return result


def _fill_channel_table(slide, channel):
    rows = channel.head(4).reset_index(drop=True) if channel is not None else pd.DataFrame()
    ys = [2.27, 2.71, 3.13, 3.56]
    xs = {1.84: "cases", 2.64: "share_pct", 3.29: "new_wards", 4.19: "note"}
    shapes = _table_value_shapes(slide, ys, xs)
    for i, y in enumerate(ys):
        if i < len(rows):
            r = rows.iloc[i]
            values = {
                "cases": f"{int(r['cases']):,}",
                "share_pct": f"{float(r['share_pct']):.1f}%",
                "new_wards": "—",
                "note": "Review timing/coverage",
            }
        else:
            values = {k: "—" for k in xs.values()}
        for x, key in xs.items():
            if (y, x) in shapes:
                _set_text_preserve_style(shapes[(y, x)], values[key])
        # Channel name cell is left as the template's label for first four rows when possible.
        if i < len(rows):
            for sh in slide.shapes:
                if hasattr(sh, "text") and round(sh.top / 914400, 2) == y and round(sh.left / 914400, 2) == 0.59:
                    _set_text_preserve_style(sh, str(rows.iloc[i]["value"]))


def _fill_services_table(slide, category1):
    rows = category1.head(3).reset_index(drop=True) if category1 is not None else pd.DataFrame()
    ys = [2.31, 2.77, 3.23]
    xs = {8.24: "cases", 8.94: "share_pct", 9.59: "comment"}
    shapes = _table_value_shapes(slide, ys, xs)
    for i, y in enumerate(ys):
        if i < len(rows):
            r = rows.iloc[i]
            values = {"cases": f"{int(r['cases']):,}", "share_pct": f"{float(r['share_pct']):.1f}%", "comment": "Demand indicator"}
            name = str(r["value"])
        else:
            values = {k: "—" for k in xs.values()}; name = "—"
        for x, key in xs.items():
            if (y, x) in shapes:
                _set_text_preserve_style(shapes[(y, x)], values[key])
        for sh in slide.shapes:
            if hasattr(sh, "text") and round(sh.top / 914400, 2) == y and round(sh.left / 914400, 2) == 6.19:
                _set_text_preserve_style(sh, name)


def _cleanup_unused_placeholders(prs):
    """Never leave template placeholder tokens in a delivered report.
    Where a value is genuinely unavailable, use an explicit zero/zero-target
    convention rather than misleading prose or bracketed placeholders.
    """
    replacements = {
        "[##/target]": "0/0",
        "[##/##]": "0/0",
        "[##%]": "0%",
        "[##]": "0",
        "[target]": "0",
        "[summary]": "0",
        "[Best-performing municipality/region]": "Not available",
        "[largest gap]": "Not available",
        "[previous close]": "not supplied",
        "[Today / week-to-date]": "Current reporting period",
        "[Call / verify / close]": "Call / verify / close",
        "[Case ref]": "0",
        "[Ward]": "0",
        "[Service]": "Not available",
    }
    for slide in prs.slides:
        for shape in slide.shapes:
            if not hasattr(shape, "text_frame"):
                continue
            original = shape.text
            new = original
            for old, val in replacements.items():
                new = new.replace(old, val)
            # Any remaining bracketed ##-style placeholder becomes 0.
            new = re.sub(r"\[##(?:/##|/target)?\]", "0", new)
            if new != original:
                _set_text_preserve_style(shape, new)


def generate_powerpoint(template_path: str | Path, output_path: str | Path, analysis: dict, intelligence: dict, municipality: str, reporting_date, period_covered: str, close_time: str, audience_view=None, voc_analysis=None):
    prs = Presentation(str(template_path))
    summary = analysis["summary"]
    corridor = municipality or "OOP Corridor"
    date_str = reporting_date.strftime("%d %B %Y") if hasattr(reporting_date, "strftime") else str(reporting_date)
    period = period_covered or "Not specified"
    close = close_time if isinstance(close_time, str) else close_time.strftime("%H:%M")
    coverage = f"{summary['ward_coverage_pct']:.1f}%" if summary.get("ward_coverage_pct") is not None else "Not configured"
    covered = int(summary.get("distinct_wards", 0))
    total = summary.get("total_wards") or "—"
    missing = summary.get("missing_wards") if summary.get("missing_wards") is not None else "—"
    voc_n = int(voc_analysis.get("responses", 0)) if voc_analysis else 0
    status = "GREEN" if summary.get("invalid_case_records", 0) == 0 and (summary.get("ward_coverage_pct") in (None, 100)) else "AMBER"

    common = {
        "[CORRIDOR NAME]": corridor,
        "[MUNICIPALITIES / REGIONS]": corridor,
        "[REPORTING DATE]": date_str,
        "[PERIOD COVERED]": period,
        "[DATA CLOSE TIME]": close,
    }
    for slide in prs.slides:
        _replace_all_tokens(slide, common)
        _set_rag(slide, status)
        # Preserve the template footer style; only replace content.
        for sh in slide.shapes:
            if hasattr(sh, "text") and "INTERNAL SDI OPERATIONS REPORTING" in sh.text:
                _set_text_preserve_style(sh, f"{corridor} | INTERNAL SDI OPERATIONS REPORTING | {date_str} | {close}")
            if hasattr(sh, "text") and sh.text.strip() == "Template: replace all [bracketed] fields and sample chart data":
                _set_text_preserve_style(sh, "Generated from approved corridor template")

    # Slide 1: exact KPI cards.
    s = prs.slides[0]
    kpis = [f"{summary['valid_cases']:,}", f"{covered}/{total}", coverage, str(missing), f"{voc_n:,}" if voc_analysis else "Not supplied", status]
    kpi_boxes = [sh for sh in s.shapes if hasattr(sh, "text") and sh.text.strip() in {"[##]", "[##/##]", "[##%]", "[RAG]"}]
    # Existing six KPI value boxes occur in known left-to-right order.
    value_shapes = [s.shapes[i] for i in [6,9,12,15,18,21]]
    for sh, val in zip(value_shapes, kpis):
        _set_text_preserve_style(sh, val)
    _set_rag(s, status)

    # Slide 2: text + existing bars + existing table.
    s = prs.slides[1]
    _replace_exact(s, "[##] valid cases opened [##] of [target] wards ([##%]). [Best-performing municipality/region] leads coverage; [largest gap] carries the largest missing-ward load.",
                   f"{summary['valid_cases']:,} valid cases across {covered} of {total} configured wards ({coverage}).")
    _replace_exact(s, "[Today / week-to-date] added [##] new wards and [##] cases compared with [previous close]. Note material increases or flat movement only.",
                   f"Observed extract: {summary['records']:,} records. Prior-close comparison is not supplied.")
    _replace_exact(s, "[##] wards remain uncovered. Prioritise wards carried over from the previous close and any channel/time gaps affecting coverage.",
                   f"{missing} wards are not represented in the supplied extract. Validate the missing-ward list before circulation.")
    _replace_exact(s, "Replace with cases and new wards by day.", "Cases by reporting date")
    d = analysis.get("dates", {})
    if d.get("available"):
        day = d["by_date"].sort_values("date").tail(5)
        _render_existing_bars(s, [20,21,22,23,24], day["cases"].tolist(), horizontal=False)
        # Replace the sample day labels/case values without changing style.
        label_ids = [42,47,52,57]
        case_ids = [43,48,53,58]
        for i, (li, ci) in enumerate(zip(label_ids, case_ids)):
            if i < len(day):
                row = day.iloc[i]
                _set_text_preserve_style(s.shapes[li], str(row["date"]))
                _set_text_preserve_style(s.shapes[ci], f"{int(row['cases']):,}")
            else:
                _set_text_preserve_style(s.shapes[li], "—")
                _set_text_preserve_style(s.shapes[ci], "—")
    _replace_exact(s, "Assign missing wards by municipality/region.\nProtect high-yield calling times.\nMove detailed exceptions to addendum.",
                   "Validate missing wards against the official register.\nProtect observed peak intake periods.\nKeep detailed exceptions in the addendum.")

    # Slide 3: ward table + existing sample bars.
    s = prs.slides[2]
    _replace_exact(s, "Replace with stacked bars by municipality/region.", "Covered vs missing wards")
    # Four table rows: only the first row is the configured municipality; total is exact.
    rows = [(corridor, total, covered, missing, coverage), ("—", "—", "—", "—", "—"), ("—", "—", "—", "—", "—"), ("Total", total, covered, missing, coverage)]
    row_y = [2.27, 2.71, 3.13, 3.56]
    xmap = {2.74: 1, 3.56: 2, 4.42: 3, 5.28: 4}
    for y, row in zip(row_y, rows):
        for sh in s.shapes:
            if not hasattr(sh, "text") or round(sh.top/914400,2) != y: continue
            x = round(sh.left/914400,2)
            if x == 0.59: _set_text_preserve_style(sh, row[0])
            elif x in xmap: _set_text_preserve_style(sh, str(row[xmap[x]]))
    _render_existing_bars(s, [46,47,48,49,50], [covered, 0, 0, missing, covered], horizontal=False, max_value=max(int(total) if str(total).isdigit() else covered, covered, missing, 1))
    _replace_exact(s, "The addendum must carry the full accounted and missing ward list with area/sub-place names, carried-over flags and assigned owner.",
                   "The addendum carries the represented-ward evidence. Missing-ward names require an approved ward master/reference list.")

    # Slide 4: channel table, existing bars, and observed hourly bars.
    s = prs.slides[3]
    _replace_exact(s, "Replace with cases by channel or channel share.", "Channel mix")
    _fill_channel_table(s, analysis.get("channel"))
    ch = analysis.get("channel")
    if ch is not None and not ch.empty:
        _render_existing_bars(s, [46,47,48,49,50], ch.head(5)["cases"].tolist(), horizontal=False)
    _replace_exact(s, "Replace with cases by hour and cumulative new wards.", "Observed case-creation activity")
    if d.get("available"):
        hourly = d["by_hour"]
        _render_existing_bars(s, [55,56,57,58,59], hourly["cases"].tolist()[:5], horizontal=False)
        first_time = d.get("day_min_time") or d.get("min")
        last_time = d.get("day_max_time") or d.get("max")
        peak = d.get("peak_hour")
        note = f"Observed window: {first_time:%H:%M}–{last_time:%H:%M}. Peak: {peak:02d}:00 ({int(d['peak_hour_cases']):,})." if hasattr(first_time, "strftime") and hasattr(last_time, "strftime") else f"Peak observed hour: {peak:02d}:00 ({int(d['peak_hour_cases']):,})."
        _replace_exact(s, "Show only actionable timing patterns: peak intake hours, quiet periods, missed activity windows and the observed first/last record time.", note)

    # Slide 5: demand bars/table.
    s = prs.slides[4]
    _replace_exact(s, "Replace with top 5-8 services by cases.", "Top demand categories")
    _fill_services_table(s, analysis.get("category1"))
    cat = analysis.get("category1")
    if cat is not None and not cat.empty:
        _render_existing_bars(s, [11,12,13,14,15], cat.head(5)["cases"].tolist(), horizontal=False)
    _replace_exact(s, "List services not yet seen or single-service wards that require probing during callbacks. This keeps the slide operational without overcrowding it.",
                   "Use the addendum for low-volume services and single-service ward follow-up.")

    # Slide 6: VOC, using supplied workbook if available.
    s = prs.slides[5]
    if voc_analysis:
        vocvals = [str(voc_analysis.get("responses", 0)), voc_analysis.get("happiness", "Not calculated"), str(voc_analysis.get("resolved", "Not calculated")), str(voc_analysis.get("survey_ready", "Not calculated")), "Available"]
        value_shapes = [s.shapes[i] for i in [10,13,16,19,22]]
        for sh, val in zip(value_shapes, vocvals): _set_text_preserve_style(sh, val)
        _replace_exact(s, "If no date-aligned VOC dataset is supplied, report availability as 'Not supplied' and do not infer happiness, effort, satisfaction or NPS. Put anomaly detail in the addendum.",
                       "VOC source supplied. Metrics shown are calculated only where the response fields support them; detailed responses remain in the addendum.")
    else:
        vals = ["Not supplied", "Not calculated", "Not calculated", "Not calculated", "Not supplied"]
        for sh, val in zip([s.shapes[i] for i in [10,13,16,19,22]], vals): _set_text_preserve_style(sh, val)

    # Slide 7: action table and existing priority bars.
    s = prs.slides[6]
    ys = [2.42, 2.94, 3.46, 3.98]
    action_rows = [
        ("Missing wards", "Ops lead", "Next close", f"{missing} wards validated/assigned"),
        ("Channel/time gap", "Supervisor", "Next operating window", "Peak hours protected"),
        ("VOC queue", "VOC lead", "When VOC source is supplied", "VOC-ready dataset"),
        ("Data quality", "Data lead", "Before circulation", f"{len(analysis.get('quality', []))} quality findings reviewed"),
    ]
    for y, vals in zip(ys, action_rows):
        for sh in s.shapes:
            if not hasattr(sh, "text") or round(sh.top/914400,2) != y: continue
            x = round(sh.left/914400,2)
            mp={0.59:vals[0],2.24:vals[1],3.59:vals[2],4.84:vals[3]}
            if x in mp: _set_text_preserve_style(sh, mp[x])
    _render_existing_bars(s, [40,41,42,43,44], [missing, 1 if ch is not None and not ch.empty else 0, int(voc_analysis.get("responses",0)) if voc_analysis else 0, len(analysis.get("quality", [])), 1], horizontal=False)
    _replace_exact(s, "[State one clear management decision or escalation required.]", f"Confirm and assign the {missing} unrepresented wards before the next operational close.")
    _replace_exact(s, "[State the only caveat that changes interpretation: data cut-off, missing source, or unresolved validation.]", "Area-level municipality breakdown requires a validated ward/master reference mapping.")
    _replace_exact(s, "Detailed graphs, accounted wards, missing wards, time logs and correction registers are attached separately.", "Detailed graphs, ward evidence, time logs, VOC evidence and QA registers are in the analytical addendum.")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))
    return Path(output_path)
