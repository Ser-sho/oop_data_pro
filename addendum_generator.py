from __future__ import annotations
from pathlib import Path
from typing import Any
import re
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.label import DataLabelList

GREEN = 'E2F0D9'
AMBER = 'FFF2CC'
RED = 'FCE4D6'
NAVY = '17324D'
BLUE = 'D9EAF7'
WHITE = 'FFFFFF'
GREY = 'F3F6FA'
DARK = '263238'


def _safe_sheet(name: str) -> str:
    for ch in '[]:*?/\\':
        name = name.replace(ch, '_')
    return name[:31]


def _frame(df: pd.DataFrame | None, note='No records available for this section.') -> pd.DataFrame:
    if isinstance(df, pd.DataFrame) and not df.empty:
        return df.copy()
    return pd.DataFrame({'Note': [note]})


def _rag_fill(value: Any):
    v = str(value or '').strip().lower()
    if v in {'green','pass','ready','controlled','good','complete','available'}:
        return PatternFill('solid', fgColor=GREEN)
    if v in {'amber','review','open','warning','partial','medium','held','not supplied','not available'}:
        return PatternFill('solid', fgColor=AMBER)
    if v in {'red','fail','blocked','critical','high','poor'}:
        return PatternFill('solid', fgColor=RED)
    return None


def _overall_rag(analysis: dict[str, Any], intelligence: dict[str, Any], voc_analysis=None) -> str:
    q = analysis.get('quality')
    if isinstance(q, pd.DataFrame) and not q.empty:
        vals = ' '.join(q.astype(str).fillna('').agg(' '.join, axis=1).tolist()).lower()
        if 'critical' in vals or 'high' in vals or 'fail' in vals:
            return 'Red'
        return 'Amber'
    qa = intelligence.get('final_report_qa')
    if isinstance(qa, pd.DataFrame) and not qa.empty and 'status' in qa.columns:
        if qa['status'].astype(str).str.upper().eq('FAIL').any():
            return 'Red'
        if qa['status'].astype(str).str.upper().isin(['WARNING','REVIEW']).any():
            return 'Amber'
    cov = (analysis.get('summary', {}) or {}).get('ward_coverage_pct')
    if isinstance(cov, (int, float)):
        if cov >= 100: return 'Green'
        if cov == 0: return 'Red'
        return 'Amber'
    return 'Green'


def _write_table(ws, start_row: int, df: pd.DataFrame, title: str | None = None, rag_col: str | None = None) -> int:
    if title:
        ws.cell(start_row, 1, title).font = Font(bold=True, size=13, color=NAVY)
        start_row += 1
    df = _frame(df)
    for j, col in enumerate(df.columns, 1):
        c = ws.cell(start_row, j, str(col))
        c.font = Font(bold=True, color=DARK)
        c.fill = PatternFill('solid', fgColor=BLUE)
        c.alignment = Alignment(wrap_text=True, vertical='center')
    for i, row in enumerate(df.itertuples(index=False), start_row + 1):
        for j, val in enumerate(row, 1):
            c = ws.cell(i, j, '' if pd.isna(val) else val)
            c.alignment = Alignment(wrap_text=True, vertical='top')
        if rag_col and rag_col in df.columns:
            ridx = list(df.columns).index(rag_col) + 1
            fill = _rag_fill(ws.cell(i, ridx).value)
            if fill:
                ws.cell(i, ridx).fill = fill
    return start_row + len(df) + 2


def _style_sheet(ws, tab_rag='Green'):
    ws.freeze_panes = 'A2'
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = {'Green': GREEN, 'Amber': AMBER, 'Red': RED}.get(tab_rag, GREEN)
    for col in range(1, ws.max_column + 1):
        letter = get_column_letter(col)
        vals = [ws.cell(r, col).value for r in range(1, min(ws.max_row, 160) + 1)]
        mx = max([len(str(v)) for v in vals if v is not None] or [10])
        ws.column_dimensions[letter].width = min(max(mx + 2, 11), 48)
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None:
                cell.alignment = Alignment(wrap_text=True, vertical='top')


def _top_table(df: pd.DataFrame | None, n=10):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return _frame(None)
    return df.copy().head(n)


def _write_insight(ws, row: int, heading: str, text: str, rag='Amber') -> int:
    ws.cell(row, 1, heading).font = Font(bold=True, color=NAVY, size=11)
    ws.cell(row, 2, text)
    ws.cell(row, 1).fill = PatternFill('solid', fgColor=GREY)
    ws.cell(row, 2).fill = _rag_fill(rag) or PatternFill('solid', fgColor=GREY)
    ws.cell(row, 1).alignment = Alignment(wrap_text=True, vertical='top')
    ws.cell(row, 2).alignment = Alignment(wrap_text=True, vertical='top')
    return row + 2


def _add_bar_chart(ws, title: str, data_start: int, data_end: int, cat_col: int, val_col: int, anchor: str, width=13, height=7, x_axis_title='Cases'):
    if data_end < data_start:
        return
    chart = BarChart()
    chart.type = 'bar'
    chart.style = 10
    chart.title = title
    chart.y_axis.title = ''
    chart.x_axis.title = x_axis_title
    data = Reference(ws, min_col=val_col, min_row=data_start - 1, max_row=data_end)
    cats = Reference(ws, min_col=cat_col, min_row=data_start, max_row=data_end)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.height = height
    chart.width = width
    chart.legend = None
    chart.varyColors = False
    ws.add_chart(chart, anchor)


def _add_line_chart(ws, title: str, data_start: int, data_end: int, cat_col: int, val_col: int, anchor: str, width=14, height=7):
    if data_end < data_start:
        return
    chart = LineChart()
    chart.style = 13
    chart.title = title
    chart.y_axis.title = 'Cases'
    chart.x_axis.title = ''
    data = Reference(ws, min_col=val_col, min_row=data_start - 1, max_row=data_end)
    cats = Reference(ws, min_col=cat_col, min_row=data_start, max_row=data_end)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.height = height
    chart.width = width
    chart.legend = None
    ws.add_chart(chart, anchor)


def _period_context(period_type: str, audience: str, requirements: str, analysis_mode: str) -> tuple[str, int]:
    text = f'{audience} {requirements}'.lower()
    if 'analyst' in text:
        detail = 'Analyst'
    elif 'executive' in text or 'senior' in text:
        detail = 'Executive'
    elif 'operations' in text or 'operational' in text:
        detail = 'Operations'
    else:
        detail = 'Balanced'
    n = {'Executive': 5, 'Operations': 10, 'Analyst': 15, 'Balanced': 8}[detail]
    if analysis_mode == 'Extreme Analysis' and detail == 'Executive':
        n = 8
    return detail, n


def _clean_daily(df: pd.DataFrame | None) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty or 'cases' not in df.columns:
        return pd.DataFrame(columns=['date', 'cases'])
    out = df.copy()
    if 'date' not in out.columns:
        return pd.DataFrame(columns=['date', 'cases'])
    out['date'] = pd.to_datetime(out['date'], errors='coerce')
    out['cases'] = pd.to_numeric(out['cases'], errors='coerce')
    return out.dropna(subset=['date', 'cases']).sort_values('date')



def _fmt_pct(v: Any) -> str:
    try:
        return f"{float(v):.1f}%"
    except Exception:
        return "not available"


def _dynamic_insights(analysis: dict[str, Any], period_evidence: dict[str, Any], period_summary: dict[str, Any] | None, period_type: str, audience: str, requesting_team: str, requirements: str) -> dict[str, tuple[str, str]]:
    """Create evidence-derived management insights for each addendum section.

    These are deliberately deterministic: they describe observed concentration,
    movement and control implications without inventing causes or performance claims.
    """
    out: dict[str, tuple[str, str]] = {}
    ev = period_evidence or {}
    n = int(ev.get('case_count', 0) or 0)

    status = ev.get('status') if isinstance(ev.get('status'), pd.DataFrame) else pd.DataFrame()
    if not status.empty:
        top = status.iloc[0]
        active = int(ev.get('workflow', {}).get('active', 0) or 0)
        resolved = int(ev.get('workflow', {}).get('resolved', 0) or 0)
        if active + resolved:
            out['workflow'] = (
                f"{top['value']} is the largest status at {int(top['cases']):,} cases ({_fmt_pct(top['share_pct'])}). "
                f"The active-to-resolved position is {active:,} to {resolved:,}; this is a workload position, not a service-quality judgement.",
                'Amber' if active > resolved and active else 'Green'
            )

    channel = ev.get('channel') if isinstance(ev.get('channel'), pd.DataFrame) else pd.DataFrame()
    if not channel.empty:
        top = channel.iloc[0]
        out['channel'] = (
            f"{top['value']} accounts for {int(top['cases']):,} of {n:,} period cases ({_fmt_pct(top['share_pct'])}). "
            "Capacity and intake controls should be reviewed around this channel before interpreting the concentration as a cause.",
            'Amber' if float(top.get('share_pct', 0)) >= 80 else 'Green'
        )

    daily = _clean_daily(ev.get('daily'))
    if period_type != 'Daily' and not daily.empty:
        peak = daily.loc[daily['cases'].idxmax()]
        out['channel_time'] = (
            f"Daily activity peaked on {pd.Timestamp(peak['date']).strftime('%d %b %Y')} at {int(peak['cases']):,} cases. "
            f"The trend contains {len(daily):,} observed day(s); use the pattern for workload planning rather than causal inference.",
            'Green'
        )
    elif period_type == 'Daily':
        hourly = analysis.get('dates', {}).get('by_hour')
        if isinstance(hourly, pd.DataFrame) and not hourly.empty:
            peak = hourly.loc[hourly['cases'].idxmax()]
            out['channel_time'] = (
                f"Activity peaked at {int(peak['hour']):02d}:00 with {int(peak['cases']):,} cases on the selected reporting date. "
                "The peak identifies arrival timing; it does not explain the underlying demand.",
                'Green'
            )

    cat = ev.get('category1') if isinstance(ev.get('category1'), pd.DataFrame) else pd.DataFrame()
    if not cat.empty:
        top = cat.iloc[0]
        top3 = float(cat.head(3)['share_pct'].sum()) if 'share_pct' in cat.columns else 0
        out['demand'] = (
            f"{top['value']} is the leading demand category with {int(top['cases']):,} cases ({_fmt_pct(top['share_pct'])}). "
            f"The top three categories represent about {top3:.1f}% of period demand, making them the first candidates for operational drill-down.",
            'Amber' if top3 >= 50 else 'Green'
        )

    city = ev.get('city') if isinstance(ev.get('city'), pd.DataFrame) else pd.DataFrame()
    if not city.empty:
        top = city.iloc[0]
        out['location'] = (
            f"{top['value']} has the highest period volume at {int(top['cases']):,} cases ({_fmt_pct(top['share_pct'])}). "
            "Location concentration should be cross-checked with service mix and ward coverage before assigning an operational cause.",
            'Amber' if float(top.get('share_pct', 0)) >= 20 else 'Green'
        )

    priority = ev.get('priority') if isinstance(ev.get('priority'), pd.DataFrame) else pd.DataFrame()
    if not priority.empty:
        high = priority[priority['value'].astype(str).str.lower().isin(['high','critical','rapid response'])]['cases'].sum() if 'value' in priority.columns else 0
        high_pct = (high / n * 100) if n else 0
        out['priority'] = (
            f"Higher-priority categories account for {int(high):,} cases ({high_pct:.1f}%) of the selected period. "
            "This is the portion to use for triage and escalation review; priority labels do not independently prove risk severity.",
            'Amber' if high_pct >= 10 else 'Green'
        )

    cov = analysis.get('corridor_coverage')
    if isinstance(cov, pd.DataFrame) and not cov.empty and 'coverage_pct' in cov.columns:
        low = cov.sort_values('coverage_pct').iloc[0]
        avg = float(cov['covered'].sum()) / float(cov['target'].sum()) * 100 if float(cov['target'].sum()) else 0
        if period_type == 'Daily':
            sd = analysis.get('dates', {}).get('selected_day', {}) or {}
            running = sd.get('running_wards')
            daily_wards = sd.get('new_wards', 0)
            running_text = f" The reporting-week running position is {int(running):,} wards ({int(running)/float(cov['target'].sum())*100:.1f}%)" if isinstance(running, (int,float)) and float(cov['target'].sum()) else ''
            out['coverage'] = (
                f"Selected-day representation is {int(daily_wards):,} newly represented ward(s), while the corridor benchmark shows {avg:.1f}% coverage for the selected operating position. {low['corridor']} has the lowest corridor coverage at {_fmt_pct(low['coverage_pct'])}." + running_text + ". Unrepresented wards are an evidence-coverage gap, not evidence of zero service demand.",
                'Amber' if avg < 80 else 'Green'
            )
        else:
            represented = ev.get('distinct_wards_matched', ev.get('distinct_wards'))
            total_unique = (analysis.get('summary', {}) or {}).get('ward_master_unique_wards') or (analysis.get('summary', {}) or {}).get('total_wards')
            total = float(total_unique) if isinstance(total_unique, (int,float)) else float(cov['target'].sum())
            pct = float(represented) / total * 100 if isinstance(represented, (int,float)) and total else avg
            outside = int(ev.get('wards_outside_master', 0) or 0)
            outside_text = f" {outside} ward value(s) fall outside the supplied ward master and are retained as exceptions." if outside else ''
            out['coverage'] = (
                f"The selected period represents {int(represented):,} of {int(total):,} unique configured wards ({pct:.1f}%). {low['corridor']} has the lowest corridor coverage at {_fmt_pct(low['coverage_pct'])}. Unrepresented wards are an evidence-coverage gap, not evidence of zero service demand." + outside_text,
                'Amber' if pct < 80 or outside else 'Green'
            )

    q = analysis.get('quality')
    if isinstance(q, pd.DataFrame) and not q.empty:
        sev = q['severity'].astype(str).str.lower() if 'severity' in q.columns else pd.Series(dtype=str)
        high = int(sev.isin(['high','critical']).sum())
        out['quality'] = (
            f"{len(q):,} deterministic data-quality exception(s) are recorded" + (f", including {high:,} high/critical item(s)." if high else ".") + " Affected fields should be treated as controlled limitations in downstream decisions.",
            'Red' if high else 'Amber'
        )
    else:
        out['quality'] = ('No mapped deterministic quality exceptions were identified in the supplied control checks.', 'Green')

    if period_summary and isinstance(period_summary.get('change_pct'), (int, float)):
        ch = float(period_summary['change_pct'])
        direction = 'increased' if ch > 0 else 'decreased' if ch < 0 else 'was unchanged'
        out['period'] = (
            f"Period volume {direction} by {abs(ch):.1f}% versus the configured comparison period ({int(period_summary.get('comparison_records', 0) or 0):,} comparison cases versus {n:,} current cases). "
            "The movement should be checked against demand, process and data-capture changes before assigning a cause.",
            'Amber' if abs(ch) >= 20 else 'Green'
        )

    return out

def _extreme_registers(intelligence: dict[str, Any]) -> dict[str, pd.DataFrame]:
    ex = intelligence.get('extreme_analysis')
    if not isinstance(ex, dict):
        ex = {}
    # App V3.11.2 stores the registers under these names; keep fallbacks for
    # workbooks generated from earlier builds.
    return {
        'findings': _frame(ex.get('findings') if isinstance(ex.get('findings'), pd.DataFrame) else intelligence.get('v39_extreme_findings')),
        'pareto': _frame(ex.get('pareto')),
        'profile': _frame(ex.get('segment_profile')),
        'diagnostic': _frame(ex.get('diagnostic_relationships')),
        'fishbone': _frame(ex.get('fishbone')),
        'five_whys': _frame(ex.get('five_whys')),
        'predictive': _frame(ex.get('predictive_series')),
        'evidence': _frame(ex.get('evidence')),
        'qa': _frame(ex.get('qa')),
        'systemic': ex.get('systemic_investigation', {}) if isinstance(ex.get('systemic_investigation', {}), dict) else {},
    }


def generate_addendum(
    output_path: str | Path,
    source_filename: str,
    sheet_name: str,
    analysis: dict[str, Any],
    intelligence: dict[str, Any],
    municipality: str,
    reporting_date,
    period_covered: str,
    close_time: str,
    voc_analysis=None,
    entity_context: dict[str, Any] | None = None,
    period_evidence: dict[str, Any] | None = None,
    reporting_period: Any | None = None,
    analysis_mode: str = 'Normal Analysis',
    audience: str = 'Executive management',
    requesting_team: str = '',
    report_requirements: str = '',
    period_summary: dict[str, Any] | None = None,
) -> Path:
    """Create an adaptive management/evidence addendum.

    Normal mode remains concise. Extreme mode adds diagnostic evidence only when
    those registers exist. Audience, period and stated requirements determine the
    amount of detail and which charts are most useful. Unsupported evidence is
    shown as unavailable rather than invented.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    period_evidence = period_evidence or {}
    entity = (entity_context or {}).get('entity', {}) or {}
    team = (entity_context or {}).get('team', {}) or {}
    overall = _overall_rag(analysis, intelligence, voc_analysis)
    period_type = getattr(reporting_period, 'period_type', '') if reporting_period is not None else ''
    detail, top_n = _period_context(period_type, audience, report_requirements, analysis_mode)
    is_extreme = analysis_mode == 'Extreme Analysis'
    insights = _dynamic_insights(analysis, period_evidence, period_summary, period_type, audience, requesting_team, report_requirements)

    wb = Workbook()
    wb.remove(wb.active)

    # 1. Report Summary
    ws = wb.create_sheet('Report Summary')
    ws['A1'] = f"{entity.get('department', 'Operations')} — Operational Addendum"
    ws['A1'].font = Font(bold=True, size=18, color=NAVY)
    ws['A2'] = f"{municipality} | {period_covered or reporting_date.isoformat()} | {analysis_mode} | {audience}"
    ws['A2'].font = Font(size=10, color='5C6B78')
    ws['A4'] = 'Overall RAG'; ws['B4'] = overall; ws['B4'].fill = _rag_fill(overall); ws['B4'].font = Font(bold=True)
    context = pd.DataFrame([
        ['Department / entity', entity.get('department', 'Not specified')],
        ['Requesting team', requesting_team or team.get('team', 'Not specified')],
        ['Audience', audience],
        ['Analysis mode', analysis_mode],
        ['Reporting period type', period_type or 'Not specified'],
        ['Municipality / corridor', municipality],
        ['Reporting date', reporting_date.isoformat()],
        ['Period covered', period_covered or 'Not specified'],
        ['Data close time', close_time],
        ['Source file', source_filename],
        ['Source sheet', sheet_name],
        ['Records analysed', (analysis.get('summary', {}) or {}).get('records', 'Not available')],
        ['Valid cases', (analysis.get('summary', {}) or {}).get('valid_cases', 'Not available')],
        ['Configured ward benchmark', (analysis.get('summary', {}) or {}).get('total_wards', 'Not configured')],
        ['Distinct wards represented', (analysis.get('summary', {}) or {}).get('distinct_wards', 'Not available')],
        ['Ward coverage %', (analysis.get('summary', {}) or {}).get('ward_coverage_pct', 'Not available')],
    ], columns=['Item', 'Value'])
    r = _write_table(ws, 6, context, 'Report context')
    s = analysis.get('summary', {}) or {}; dates = analysis.get('dates', {}) or {}
    key = pd.DataFrame([
        ['Cases in selected period', period_evidence.get('case_count', s.get('valid_cases', 'Not available')), 'Period-aligned denominator used for this report'],
        ['Selected-day cases', dates.get('selected_day', {}).get('cases', 'Not available'), 'Relevant when the period is Daily or when a daily anchor is required'],
        ['Distinct period wards', period_evidence.get('distinct_wards', s.get('distinct_wards', 'Not available')), 'Distinct wards represented in the selected period'],
        ['Period-over-period change', (period_summary or {}).get('change_pct', 'Not available'), 'Comparison supplied by the period engine; percentage is relative to its configured comparison period'],
        ['Data quality position', 'Exceptions present' if isinstance(analysis.get('quality'), pd.DataFrame) and not analysis['quality'].empty else 'No mapped exceptions', 'Deterministic control findings'],
    ], columns=['Metric', 'Value', 'Calculation / interpretation'])
    _write_table(ws, r, key, 'Key operating measures')
    insight = 'Management-facing summary; detailed calculations and diagnostics are separated below.'
    if is_extreme:
        insight = 'Extreme mode is additive: the normal operating evidence remains intact, while deeper diagnostic/predictive registers are included only where the evidence gate supports them.'
    _write_insight(ws, ws.max_row + 1, 'Addendum design', insight, overall)
    _style_sheet(ws, overall)

    # 2. Evidence Log
    ws = wb.create_sheet('Evidence Log')
    evidence_rows = [
        ['Operational extract', source_filename, close_time, s.get('records', 'Not available'), 'Selected-period denominator is date-filtered; source fields remain authoritative.'],
        ['Ward master / reference', 'Supplied ward master', 'Controlled reference', s.get('ward_master_unique_wards', 'Not available'), 'Used as the geographic benchmark; exceptions are retained rather than silently corrected.'],
        ['Voice of Citizen', 'Supplied VoC dataset' if voc_analysis else 'Not supplied', period_covered or reporting_date.isoformat(), voc_analysis.get('responses') if voc_analysis else 'Not supplied', 'Used only where supplied fields support the metric and period alignment.'],
    ]
    if is_extreme:
        evidence_rows.append(['Extreme diagnostic registers', 'Extreme Analysis engine', period_type or 'Selected period', len(_extreme_registers(intelligence)['evidence']), 'Pareto, diagnostic, predictive and control evidence is included only where available and evidence-gated.'])
    _write_table(ws, 1, pd.DataFrame(evidence_rows, columns=['Evidence source','Reference','Date / close','Rows / records','Treatment in report']), 'Source and evidence log')
    _style_sheet(ws, overall)

    # 3. Ward Coverage
    ws = wb.create_sheet('Ward Coverage')
    cov = analysis.get('corridor_coverage')
    rr = 1
    if isinstance(cov, pd.DataFrame) and not cov.empty:
        c = cov.copy()
        if 'coverage_pct' in c.columns:
            c['RAG'] = c['coverage_pct'].apply(lambda x: 'Green' if float(x) >= 100 else ('Red' if float(x) == 0 else 'Amber'))
        elif 'covered' in c.columns and 'target' in c.columns:
            c['Coverage %'] = (c['covered'] / c['target'].replace(0, pd.NA) * 100).round(1)
            c['RAG'] = c['Coverage %'].apply(lambda x: 'Green' if pd.notna(x) and float(x) >= 100 else ('Red' if pd.notna(x) and float(x) == 0 else 'Amber'))
        rr = _write_table(ws, 1, c, 'Coverage summary', rag_col='RAG')
        if 'covered' in c.columns and 'target' in c.columns:
            if 'Coverage %' in c.columns:
                _add_bar_chart(ws, 'Coverage by corridor / CCA', 3, min(2 + top_n, 2 + len(c)), 1, list(c.columns).index('Coverage %') + 1, 'J2', x_axis_title='Coverage %')
            else:
                _add_bar_chart(ws, 'Coverage by corridor / CCA', 3, min(2 + top_n, 2 + len(c)), 1, list(c.columns).index('covered') + 1, 'J2')
    cca = analysis.get('cca_coverage')
    if isinstance(cca, pd.DataFrame) and not cca.empty:
        cc = cca.copy()
        if 'target' in cc.columns and 'covered' in cc.columns:
            cc['Coverage %'] = (cc['covered'] / cc['target'].replace(0, pd.NA) * 100).round(1)
            cc['RAG'] = cc['Coverage %'].apply(lambda x: 'Green' if pd.notna(x) and float(x) >= 100 else ('Red' if pd.notna(x) and float(x) == 0 else 'Amber'))
        rr = _write_table(ws, rr, cc, 'CCA position', rag_col='RAG')
    missing = dates.get('missing_wards')
    if isinstance(missing, pd.DataFrame) and not missing.empty and detail != 'Executive':
        _write_table(ws, rr, missing.head(top_n), 'Missing / follow-up ward queue')
    cov_text, cov_rag = insights.get('coverage', ('Coverage is a representation measure, not a service-quality score.', 'Green'))
    _write_insight(ws, ws.max_row + 1, 'Management insight', cov_text, cov_rag)
    _style_sheet(ws, 'Amber' if isinstance(missing, pd.DataFrame) and not missing.empty else 'Green')

    # 4. Channel & Time
    ws = wb.create_sheet('Channel & Time')
    ch = period_evidence.get('channel') if isinstance(period_evidence.get('channel'), pd.DataFrame) else analysis.get('channel')
    rr = 1
    if isinstance(ch, pd.DataFrame) and not ch.empty:
        rr = _write_table(ws, 1, ch.head(top_n), 'Channel mix')
        if 'cases' in ch.columns:
            val_col = list(ch.columns).index('cases') + 1
            _add_bar_chart(ws, 'Cases by channel', 3, 2 + min(top_n, len(ch)), 1, val_col, 'J2')
    hourly = dates.get('by_hour')
    if isinstance(hourly, pd.DataFrame) and not hourly.empty:
        rr = _write_table(ws, rr, hourly, 'Hourly activity')
        if detail != 'Executive' and 'cases' in hourly.columns:
            _add_bar_chart(ws, 'Cases by hour', rr - len(hourly) - 1, rr - 2, 1, list(hourly.columns).index('cases') + 1, 'J18')
    daily = _clean_daily(period_evidence.get('daily'))
    if period_summary and isinstance(period_summary.get('comparison_daily'), pd.DataFrame) and not period_summary['comparison_daily'].empty:
        comp = _clean_daily(period_summary['comparison_daily']).rename(columns={'cases':'comparison_cases'})
        if not comp.empty and not daily.empty:
            # Keep comparison evidence available for analysts/operations without
            # forcing it into the executive-facing chart.
            merged = pd.concat([daily.assign(series='Selected period'), comp.assign(series='Comparison period')], ignore_index=True)
            if detail != 'Executive' and period_type != 'Daily':
                rr = _write_table(ws, rr, merged, 'Period comparison evidence')
    if period_type != 'Daily' and not daily.empty:
        rr = _write_table(ws, rr, daily, f'{period_type} daily activity')
        _add_line_chart(ws, f'{period_type} daily case trend', rr - len(daily) - 1, rr - 2, 1, list(daily.columns).index('cases') + 1, 'J34')
    ch_text, ch_rag = insights.get('channel_time', insights.get('channel', ('Channel and time show when/how demand arrived; they do not establish cause.', 'Green')))
    _write_insight(ws, ws.max_row + 1, 'Management insight', ch_text, ch_rag)
    if 'period' in insights and period_type != 'Daily':
        _write_insight(ws, ws.max_row + 1, 'Period movement', insights['period'][0], insights['period'][1])
    _style_sheet(ws, 'Green')

    # 5. Demand & Service
    ws = wb.create_sheet('Demand & Service')
    cat1 = period_evidence.get('category1') if isinstance(period_evidence.get('category1'), pd.DataFrame) else analysis.get('category1')
    rr = _write_table(ws, 1, _top_table(cat1, top_n), 'Case Category 1 — leading demand')
    if isinstance(cat1, pd.DataFrame) and not cat1.empty and 'cases' in cat1.columns:
        _add_bar_chart(ws, 'Cases by service demand', 3, 2 + min(top_n, len(cat1)), 1, list(cat1.columns).index('cases') + 1, 'J2')
    rr = _write_table(ws, rr, _top_table(period_evidence.get('category2') if isinstance(period_evidence.get('category2'), pd.DataFrame) else analysis.get('category2'), top_n), 'Case Category 2 — supporting detail')
    loc_df = period_evidence.get('city') if isinstance(period_evidence.get('city'), pd.DataFrame) else analysis.get('city')
    if detail != 'Executive' and isinstance(loc_df, pd.DataFrame) and not loc_df.empty:
        loc_start = rr
        rr = _write_table(ws, rr, _top_table(loc_df, top_n), 'Cases by location')
        if 'cases' in loc_df.columns:
            _add_bar_chart(ws, 'Cases by location', loc_start + 2, loc_start + 1 + min(top_n, len(loc_df)), 1, list(loc_df.columns).index('cases') + 1, 'J20')
    if detail == 'Analyst' or is_extreme:
        rr = _write_table(ws, rr, _top_table(period_evidence.get('category3') if isinstance(period_evidence.get('category3'), pd.DataFrame) else analysis.get('category3'), top_n), 'Case Category 3 — supporting detail')
    _write_insight(ws, ws.max_row + 1, 'Management insight', insights.get('demand', ('Leading categories identify where demand is concentrated.', 'Green'))[0], insights.get('demand', ('', 'Green'))[1])
    if 'location' in insights and detail != 'Executive':
        _write_insight(ws, ws.max_row + 1, 'Location implication', insights['location'][0], insights['location'][1])
    _style_sheet(ws, 'Green')

    # 6. Workflow & Quality
    ws = wb.create_sheet('Workflow & Quality')
    status_df = period_evidence.get('status') if isinstance(period_evidence.get('status'), pd.DataFrame) else analysis.get('status_summary')
    rr = _write_table(ws, 1, status_df, 'Case status position')
    if isinstance(status_df, pd.DataFrame) and not status_df.empty and 'cases' in status_df.columns:
        _add_bar_chart(ws, 'Case status', 3, 2 + min(top_n, len(status_df)), 1, list(status_df.columns).index('cases') + 1, 'J2')
    priority_df = ev_priority = period_evidence.get('priority') if isinstance(period_evidence.get('priority'), pd.DataFrame) else analysis.get('priority')
    if isinstance(priority_df, pd.DataFrame) and not priority_df.empty:
        priority_start = rr
        rr = _write_table(ws, rr, priority_df, 'Priority mix')
        if detail != 'Executive' and 'cases' in priority_df.columns:
            _add_bar_chart(ws, 'Priority mix', priority_start + 2, priority_start + 1 + min(top_n, len(priority_df)), 1, list(priority_df.columns).index('cases') + 1, 'J20')
    q = analysis.get('quality')
    qdf = _frame(q, 'No mapped quality exceptions were detected.')
    if isinstance(qdf, pd.DataFrame) and not qdf.empty and 'severity' in qdf.columns:
        qdf = qdf.copy(); qdf['RAG'] = qdf['severity'].apply(lambda x: 'Red' if str(x).lower() in {'high','critical'} else 'Amber')
    _write_table(ws, rr, qdf, 'Data quality, anomalies and limitations', rag_col='RAG' if 'RAG' in qdf.columns else None)
    _write_insight(ws, ws.max_row + 1, 'Management insight', insights.get('quality', ('Quality exceptions define controlled limitations.', 'Green'))[0], insights.get('quality', ('', 'Green'))[1])
    if 'priority' in insights:
        _write_insight(ws, ws.max_row + 1, 'Priority implication', insights['priority'][0], insights['priority'][1])
    _style_sheet(ws, 'Red' if isinstance(q, pd.DataFrame) and not q.empty and any(str(x).lower() in {'high','critical'} for x in q.get('severity', pd.Series(dtype=str))) else ('Amber' if isinstance(q, pd.DataFrame) and not q.empty else 'Green'))

    # 7. Voice of Citizen
    ws = wb.create_sheet('Voice of Citizen')
    if voc_analysis:
        summary = pd.DataFrame([[k,v] for k,v in voc_analysis.items() if not isinstance(v,(pd.DataFrame,list,dict))], columns=['Metric','Value'])
        row = _write_table(ws, 1, summary, 'VoC summary')
        if isinstance(voc_analysis.get('service_summary'), pd.DataFrame):
            row = _write_table(ws, row + 2, voc_analysis['service_summary'].head(top_n), 'Responses by main service')
        if isinstance(voc_analysis.get('metric_by_service'), pd.DataFrame) and not voc_analysis['metric_by_service'].empty:
            row = _write_table(ws, row + 2, voc_analysis['metric_by_service'].head(top_n), 'VoC measures by service')
        if isinstance(voc_analysis.get('happiness_detail'), pd.DataFrame) and detail != 'Executive':
            row = _write_table(ws, row + 2, voc_analysis['happiness_detail'].head(top_n), 'Happiness / resolution detail')
        if isinstance(voc_analysis.get('metric_reason_detail'), pd.DataFrame) and detail != 'Executive':
            row = _write_table(ws, row + 2, voc_analysis['metric_reason_detail'].head(top_n * 3), 'Effort, satisfaction and promotion detailed reasons')
        if isinstance(voc_analysis.get('negative_queue'), pd.DataFrame) and not voc_analysis['negative_queue'].empty:
            row = _write_table(ws, row + 2, voc_analysis['negative_queue'].head(top_n), 'Negative resolution follow-up queue')
        _write_insight(ws, ws.max_row + 2, 'VoC interpretation', 'The master survey is the primary KPI source. Happiness/resolution detail and effort, satisfaction and promotion detail are supporting evidence layers. Case Ref is used for reconciliation when available; unmatched records remain disclosed rather than force-joined.', 'Amber')
        _style_sheet(ws, 'Amber' if voc_analysis.get('available_layers',1) < 3 else 'Green')
    else:
        _write_table(ws, 1, pd.DataFrame({'Note':['No Voice of Citizen master source was supplied for this report. Metrics are not inferred.']}), 'VoC availability')
        _style_sheet(ws, 'Amber')

    # 8. Actions & Decisions
    ws = wb.create_sheet('Actions & Decisions')
    actions = intelligence.get('v36_actions')
    if not isinstance(actions, pd.DataFrame) or actions.empty: actions = intelligence.get('actions')
    if not isinstance(actions, pd.DataFrame) or actions.empty: actions = intelligence.get('recommendations')
    adf = _frame(actions)
    if 'priority' in adf.columns:
        adf = adf.copy(); adf['RAG'] = adf['priority'].apply(lambda x: 'Red' if str(x).lower() in {'critical'} else ('Amber' if str(x).lower() in {'high','medium'} else 'Green'))
    _write_table(ws, 1, adf.head(top_n), 'Management action register', rag_col='RAG' if 'RAG' in adf.columns else None)
    _write_insight(ws, ws.max_row + 1, 'Decision interpretation', 'Actions are recommendations linked to evidence. Named owners and deadlines are not invented when the source or request does not provide them.', 'Amber' if isinstance(actions, pd.DataFrame) and not actions.empty else 'Green')
    if 'workflow' in insights:
        _write_insight(ws, ws.max_row + 1, 'Workflow implication', insights['workflow'][0], insights['workflow'][1])
    _style_sheet(ws, 'Amber' if isinstance(actions, pd.DataFrame) and not actions.empty else 'Green')

    # Extreme-only evidence layer: materially different from the Normal addendum.
    if is_extreme:
        ex = _extreme_registers(intelligence)

        # 9. Extreme Overview
        ws = wb.create_sheet('Extreme Overview')
        summary = intelligence.get('extreme_analysis', {}).get('summary', {}) if isinstance(intelligence.get('extreme_analysis'), dict) else {}
        overview = pd.DataFrame([
            ['Pareto concentration', 'Available' if not ex['pareto'].empty and 'Note' not in ex['pareto'].columns else 'Not available', summary.get('pareto_available', False)],
            ['Diagnostic profile', 'Available' if not ex['profile'].empty and 'Note' not in ex['profile'].columns else 'Not available', not ex['profile'].empty and 'Note' not in ex['profile'].columns],
            ['Fishbone investigation', 'Available' if not ex['fishbone'].empty and 'Note' not in ex['fishbone'].columns else 'Not available', summary.get('fishbone_available', False)],
            ['Five Whys investigation', 'Available' if not ex['five_whys'].empty and 'Note' not in ex['five_whys'].columns else 'Not available', summary.get('five_whys_available', False)],
            ['Predictive screen', 'Available' if not ex['predictive'].empty and 'Note' not in ex['predictive'].columns else 'Held / unavailable', summary.get('predictive_available', False)],
        ], columns=['Extreme analytical layer','Status','Evidence gate result'])
        _write_table(ws, 1, overview, 'Extreme analytical coverage', rag_col='Status')
        _write_insight(ws, ws.max_row + 1, 'How to use this layer', 'Extreme Analysis is an investigation pack, not a licence to claim root cause. Pareto prioritises; diagnostic relationships identify associations; Fishbone and Five Whys frame verification; predictive evidence is shown only when historical evidence is sufficient.', 'Amber')
        _style_sheet(ws, 'Amber')

        # 10. Pareto & Concentration
        ws = wb.create_sheet('Pareto & Concentration')
        p = ex['pareto']
        if 'Note' not in p.columns and not p.empty:
            rr = _write_table(ws, 1, p, f"Pareto ranking — {p.iloc[0].get('dimension','dominant dimension')}")
            if 'cases' in p.columns:
                _add_bar_chart(ws, 'Dominant segment concentration', 3, 2 + min(top_n, len(p)), 1, list(p.columns).index('cases') + 1, 'J2')
            _write_insight(ws, ws.max_row + 1, 'Pareto interpretation', f"The leading segment is {p.iloc[0].get('value')} with {int(p.iloc[0].get('cases',0)):,} cases ({float(p.iloc[0].get('share_pct',0)):.1f}%). This prioritises investigation; it does not establish causation.", 'Amber')
        else:
            _write_table(ws, 1, p, 'Pareto ranking')
        _style_sheet(ws, 'Amber')

        # 11. Diagnostic Investigation
        ws = wb.create_sheet('Diagnostic Investigation')
        rr = _write_table(ws, 1, ex['profile'].head(top_n), 'Dominant-segment evidence profile')
        if detail != 'Executive':
            rr = _write_table(ws, rr, ex['diagnostic'].head(top_n), 'Material diagnostic relationships')
        _write_insight(ws, ws.max_row + 1, 'Diagnostic interpretation', 'A material share shift means the attribute is more or less represented inside the dominant segment than in the selected-period baseline. It is an association requiring operational validation.', 'Amber')
        _style_sheet(ws, 'Amber')

        # 12. Root Cause Investigation
        ws = wb.create_sheet('Root Cause Investigation')
        rr = _write_table(ws, 1, ex['fishbone'], 'Fishbone evidence map')
        if detail != 'Executive' or ex['five_whys'].shape[0] > 0:
            _write_table(ws, rr, ex['five_whys'], 'Five Whys — evidence and verification chain')
        _write_insight(ws, ws.max_row + 1, 'Caution', 'Fishbone and Five Whys are structured investigation frameworks. Candidate causes remain hypotheses until supported by process records, narratives, ownership evidence or other corroborating data.', 'Amber')
        _style_sheet(ws, 'Amber')

        # Systemic issue / Fishbone worksheet — only when the historical evidence gate passes.
        systemic = ex.get('systemic_investigation', {}) if isinstance(ex, dict) else {}
        if isinstance(systemic, dict) and systemic.get('gate') == 'PASS':
            ws = wb.create_sheet('Systemic Issue Investigation')
            _write_insight(ws, 1, 'Systemicity gate', f"PASS — {systemic.get('gate_reason','')}", 'Amber')
            row = 4
            _write_table(ws, row, _frame(systemic.get('worksheet')), 'Fishbone-compatible matter summary')
            row = ws.max_row + 2
            _write_table(ws, row, _frame(systemic.get('candidates')).head(top_n), 'Historical systemic-pattern candidates')
            row = ws.max_row + 2
            _write_table(ws, row, _frame(systemic.get('fishbone')), 'Systemic Fishbone evidence map')
            row = ws.max_row + 2
            _write_table(ws, row, _frame(systemic.get('likely_causes')), 'Likely causes and validation status')
            row = ws.max_row + 2
            _write_table(ws, row, _frame(systemic.get('five_whys')), 'Five Whys validation chain')
            row = ws.max_row + 2
            _write_table(ws, row, _frame(systemic.get('actions')), 'Corrective / preventive action register', rag_col='RAG' if 'RAG' in _frame(systemic.get('actions')).columns else None)
            _write_insight(ws, ws.max_row + 1, 'Control rule', 'This worksheet follows the supplied Fishbone structure concept: systemicity must be demonstrated first; likely causes are hypotheses; confirmed root cause remains No until independently validated; owners and dates are not invented.', 'Amber')
            _style_sheet(ws, 'Amber')

        # 13. Predictive & Control Outlook
        ws = wb.create_sheet('Predictive & Control Outlook')
        rr = _write_table(ws, 1, ex['predictive'], 'Historical / predictive evidence')
        if 'Note' not in ex['predictive'].columns and not ex['predictive'].empty and 'date' in ex['predictive'].columns and 'cases' in ex['predictive'].columns:
            _add_line_chart(ws, 'Historical daily activity and forecast screen', 3, 2 + len(ex['predictive']), 1, list(ex['predictive'].columns).index('cases') + 1, 'J2')
        _write_table(ws, rr, ex['evidence'].head(top_n), 'Extreme evidence register')
        _write_insight(ws, ws.max_row + 1, 'Control interpretation', 'Use the predictive screen for workload planning only when the evidence gate is passed. Optimisation recommendations should follow diagnostic verification rather than precede it.', 'Amber')
        _style_sheet(ws, 'Amber')

        # 14. Extreme QA & Method
        ws = wb.create_sheet('Extreme QA & Method')
        _write_table(ws, 1, ex['qa'], 'Extreme analytical QA', rag_col='status' if 'status' in ex['qa'].columns else None)
        rules = pd.DataFrame([
            ['Pareto', 'Prioritisation, not causation'],
            ['Diagnostic profile', 'Association and share shift, not causal proof'],
            ['Fishbone', 'Evidence-linked investigation prompts'],
            ['Five Whys', 'Verification chain; causal conclusion requires additional evidence'],
            ['Predictive screen', 'Enabled only when sufficient historical observations exist'],
            ['Optimisation', 'Requires diagnostic support and explicit control evidence'],
        ], columns=['Method','Control rule'])
        _write_table(ws, ws.max_row + 2, rules, 'Extreme method controls')
        _style_sheet(ws, 'Green' if ex['qa'].empty or ('status' in ex['qa'].columns and ex['qa']['status'].eq('PASS').all()) else 'Red')

    # Final notes — normal and extreme both keep the management-facing close-out concise.
    ws = wb.create_sheet('QA & Notes')
    qa = intelligence.get('final_report_qa')
    qdf = _frame(qa, 'No final QA table supplied.')
    _write_table(ws, 1, qdf, 'Final publication QA', rag_col='status' if 'status' in qdf.columns else None)
    notes = pd.DataFrame([
        ['Privacy','No citizen names, contact details or raw narratives are intentionally reproduced in the management addendum.'],
        ['Interpretation','Charts and distributions show observed activity. Concentration does not by itself establish cause or departmental performance.'],
        ['Ward exceptions','Ward values outside the supplied master remain flagged; they are not silently reassigned.'],
        ['Audience tailoring',f'{detail} detail level selected from audience/requesting-team wording and stated requirements.'],
        ['Period tailoring',f'{period_type or "Selected period"} determines the time-series and activity detail shown.'],
        ['Extreme mode','Additional diagnostic sheets are generated only when Extreme Analysis is selected and the corresponding evidence register exists.'],
    ], columns=['Control','Note'])
    _write_table(ws, ws.max_row + 2, notes, 'Publication notes')
    _style_sheet(ws, overall)

    wb.save(output_path)
    return output_path
