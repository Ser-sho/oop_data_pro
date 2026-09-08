from __future__ import annotations
from typing import Any
import math
import pandas as pd


def _top(df: pd.DataFrame, col: str | None, n: int = 8) -> pd.DataFrame:
    if not col or col not in df.columns or df.empty:
        return pd.DataFrame(columns=['value','cases','share_pct'])
    s = df[col].astype('string').str.strip().replace({'': pd.NA, 'nan': pd.NA, 'None': pd.NA}).dropna()
    if s.empty:
        return pd.DataFrame(columns=['value','cases','share_pct'])
    out = s.value_counts().head(n).rename_axis('value').reset_index(name='cases')
    out['share_pct'] = (out['cases'] / max(len(df), 1) * 100).round(1)
    return out


def build_period_evidence(analysis: dict[str, Any], period: Any) -> dict[str, Any]:
    """Create period-aligned evidence for the automatic designer.

    The existing daily engine remains the source of daily Operations-specific
    metrics. This layer independently filters the raw source to the selected
    period so monthly/quarterly/YTD/annual decks never reuse whole-extract
    distributions by accident.
    """
    df = analysis.get('source_df', pd.DataFrame()).copy()
    cols = analysis.get('columns', {}) or {}
    created = cols.get('created_on')
    case_id = cols.get('case_id')
    if df.empty or not created or created not in df.columns:
        return {'available': False, 'reason': 'No usable Created On field was identified.', 'df': pd.DataFrame()}
    dt = pd.to_datetime(df[created], errors='coerce')
    start = pd.Timestamp(period.start_date).normalize()
    end = pd.Timestamp(period.end_date).normalize() + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    mask = dt.notna() & (dt >= start) & (dt <= end)
    if case_id and case_id in df.columns:
        mask &= df[case_id].notna()
    work = df.loc[mask].copy()
    work['_created_dt'] = dt.loc[mask]
    out: dict[str, Any] = {
        'available': True,
        'df': work,
        'start': start,
        'end': pd.Timestamp(period.end_date).normalize(),
        'case_count': int(len(work)),
        'unique_cases': int(work[case_id].nunique()) if case_id and case_id in work.columns else int(len(work)),
    }
    if not work.empty:
        out['daily'] = (work.assign(_date=work['_created_dt'].dt.normalize())
                        .groupby('_date').size().rename('cases').reset_index()
                        .rename(columns={'_date':'date'}))
    else:
        out['daily'] = pd.DataFrame(columns=['date','cases'])
    for key in ['status','channel','case_type','priority','city','category1','category2','category3','owner']:
        out[key] = _top(work, cols.get(key), 8)
    if cols.get('ward') and cols['ward'] in work.columns:
        # Prefer the normalized/mapped ward register from the analysis engine so
        # CRM-style IDs are compared consistently with the supplied ward master.
        mapped = analysis.get('ward_mapping')
        if isinstance(mapped, pd.DataFrame) and 'ward' in mapped.columns:
            wm = mapped.reindex(work.index)
            wards = wm['ward'].astype('string').str.strip().replace({'': pd.NA, 'nan': pd.NA}).dropna()
            out['distinct_wards'] = int(wards.nunique())
            if 'mapping_status' in wm.columns:
                out['distinct_wards_matched'] = int(wm.loc[wm['mapping_status'].astype(str).str.startswith('Matched'), 'ward'].dropna().astype(str).nunique())
                out['wards_outside_master'] = int(wm.loc[wm['mapping_status'].astype(str).eq('Not in ward master'), 'ward'].dropna().astype(str).nunique())
        else:
            wards = work[cols['ward']].astype('string').str.strip().replace({'': pd.NA, 'nan': pd.NA}).dropna()
            out['distinct_wards'] = int(wards.nunique())
            out['distinct_wards_matched'] = None
            out['wards_outside_master'] = None
    else:
        out['distinct_wards'] = None
        out['distinct_wards_matched'] = None
        out['wards_outside_master'] = None
    # Status counts are kept explicit for audience-specific workflow slides.
    if not out['status'].empty:
        st = out['status']
        def count_like(words):
            return int(st[st['value'].str.lower().apply(lambda x: any(w in x for w in words))]['cases'].sum())
        out['workflow'] = {
            'active': count_like(['active','open','in progress','pending']),
            'resolved': count_like(['resolved','closed','complete']),
            'cancelled': count_like(['cancel']),
        }
    else:
        out['workflow'] = {}
    return out



def _period_findings(evidence: dict[str, Any], analysis: dict[str, Any], period_summary: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    findings=[]
    n=int(evidence.get('case_count',0) or 0)
    total=analysis.get('summary',{}).get('total_wards')
    wards=evidence.get('distinct_wards')
    if wards is not None:
        if total:
            pct=wards/total*100 if total else 0
            findings.append({'id':'P-001','priority':'High' if pct<50 else 'Normal','finding':f"{wards:,} of {int(total):,} configured wards are represented in the selected period ({pct:.1f}%), leaving {max(int(total)-int(wards),0):,} unrepresented in the period evidence.", 'evidence_ref':'PER-001'})
        else:
            findings.append({'id':'P-001','priority':'Normal','finding':f"{wards:,} distinct wards are represented in the selected period; no official ward total was supplied, so coverage percentage is not calculated.", 'evidence_ref':'PER-001'})
    status=evidence.get('status',pd.DataFrame())
    if not status.empty:
        r=status.iloc[0]; findings.append({'id':'P-002','priority':'Normal','finding':f"{r['value']} is the largest period status with {int(r['cases']):,} cases ({float(r['share_pct']):.1f}%).",'evidence_ref':'PER-002'})
    channel=evidence.get('channel',pd.DataFrame())
    if not channel.empty:
        r=channel.iloc[0]; findings.append({'id':'P-003','priority':'High' if float(r['share_pct'])>=80 else 'Normal','finding':f"{r['value']} is the dominant period intake channel with {int(r['cases']):,} cases ({float(r['share_pct']):.1f}%).",'evidence_ref':'PER-003'})
    cat=evidence.get('category1',pd.DataFrame())
    if not cat.empty:
        r=cat.iloc[0]; findings.append({'id':'P-004','priority':'Normal','finding':f"{r['value']} is the leading period Case Category 1 with {int(r['cases']):,} cases ({float(r['share_pct']):.1f}%).",'evidence_ref':'PER-004'})
    priority=evidence.get('priority',pd.DataFrame())
    if not priority.empty:
        r=priority.iloc[0]; findings.append({'id':'P-005','priority':'Normal','finding':f"{r['value']} is the largest period priority segment with {int(r['cases']):,} cases ({float(r['share_pct']):.1f}%).",'evidence_ref':'PER-005'})
    if period_summary:
        ch=period_summary.get('change_pct')
        if isinstance(ch,(int,float)):
            direction='increase' if ch>0 else 'decrease' if ch<0 else 'no change'
            findings.append({'id':'P-006','priority':'High' if abs(ch)>=20 else 'Normal','finding':f"Period case volume shows a {abs(ch):.1f}% {direction} versus the configured comparison period ({int(period_summary.get('comparison_records',0) or 0):,} comparison cases vs {n:,} current cases).",'evidence_ref':'PER-006'})
    return findings


def _period_actions(findings: list[dict[str, Any]], evidence: dict[str, Any]) -> list[dict[str, Any]]:
    actions=[]
    for f in findings:
        if f['id']=='P-001' and evidence.get('distinct_wards') is not None:
            actions.append({'priority':'High','recommendation':'Validate and assign the period-unrepresented wards before treating the period as fully geographically represented.','evidence_ref':'PER-001'})
        elif f['id']=='P-003' and 'dominant' in f['finding'].lower():
            actions.append({'priority':f['priority'],'recommendation':'Review capacity and controls around the dominant intake channel for the selected period.','evidence_ref':'PER-003'})
        elif f['id']=='P-006' and f['priority']=='High':
            actions.append({'priority':'High','recommendation':'Investigate the material period-over-period volume movement and confirm whether it reflects demand, process or data-capture changes.','evidence_ref':'PER-006'})
    return actions

def _section_available(title: str, evidence: dict[str, Any], analysis: dict[str, Any]) -> bool:
    if title in {'Executive Summary', 'Actions and Management Decisions', 'Evidence and Method Note'}:
        return True
    mapping = {
        'Performance and Activity': 'daily',
        'Geographic / Coverage Position': 'distinct_wards',
        'Case Workflow / Resolution Position': 'status',
        'Service and Demand Mix': 'category1',
        'Channel and Time Activity': 'channel',
        'Location / Entity Performance': 'city',
        'Priority / Risk Position': 'priority',
        'Voice of Citizen': None,
        'Data Quality and Limitations': None,
    }
    key = mapping.get(title)
    if key is None:
        if title == 'Voice of Citizen':
            return False
        return True
    val = evidence.get(key)
    if isinstance(val, pd.DataFrame):
        return not val.empty
    return val is not None



def validate_blueprint(blueprint: dict[str, Any]) -> pd.DataFrame:
    checks = []
    slides = blueprint.get('slides', []) or []
    checks.append({'check':'Blueprint contains slides','status':'PASS' if slides else 'FAIL','detail':f'{len(slides)} slide(s) planned'})
    checks.append({'check':'No-fabrication rule enabled','status':'PASS' if blueprint.get('rules',{}).get('no_fabrication') else 'FAIL','detail':'Unsupported metrics are omitted rather than invented.'})
    checks.append({'check':'Cover includes reporting period','status':'PASS' if blueprint.get('period_label') else 'FAIL','detail':str(blueprint.get('period_label',''))})
    checks.append({'check':'Executive summary present','status':'PASS' if any(s.get('type')=='executive_summary' for s in slides) else 'FAIL','detail':'Management summary is mandatory.'})
    checks.append({'check':'Method/evidence note present','status':'PASS' if any(s.get('type')=='method' for s in slides) else 'FAIL','detail':'Evidence route is explicit.'})
    checks.append({'check':'V3.10 analysis mode declared','status':'PASS' if blueprint.get('analysis_mode') in {'Normal Analysis','Extreme Analysis'} else 'FAIL','detail':str(blueprint.get('analysis_mode',''))})
    if blueprint.get('analysis_mode') == 'Extreme Analysis':
        present={s.get('type') for s in slides}
        checks.append({'check':'Extreme diagnostic layers','status':'PASS' if ({'extreme_diagnostic_pareto','extreme_diagnostic_framework'} <= present) or not blueprint.get('maturity_plan',{}).get('available_levels',[]) else 'WARNING','detail':'Pareto and diagnostic investigation views are separated for readability.'})
        exqa = blueprint.get('extreme_analysis',{}).get('qa')
        if isinstance(exqa, pd.DataFrame):
            checks.append({'check':'Extreme analytical QA','status':'PASS' if exqa.empty or exqa['status'].eq('PASS').all() else 'FAIL','detail':'All Extreme Analysis evidence, confidence and decision-gate checks must pass.'})
        checks.append({'check':'Extreme optimisation layer','status':'PASS' if 'extreme_optimisation' in present else 'FAIL','detail':'Optimisation/control review is mandatory in Extreme Analysis.'})
    if blueprint.get('period_type') == 'Daily':
        required = {'daily_snapshot','actions','method','executive_summary'}
        present = {s.get('type') for s in slides}
        missing = sorted(required - present)
        checks.append({'check':'Daily mandatory framework present','status':'PASS' if not missing else 'FAIL','detail':'All core daily report sections are present.' if not missing else 'Missing: ' + ', '.join(missing)})
        checks.append({'check':'Daily operational coverage view','status':'PASS' if 'coverage' in present else 'WARNING','detail':'Ward/geographic coverage is included when ward evidence is available.'})
        checks.append({'check':'Daily channel/time view','status':'PASS' if 'channel_time' in present else 'WARNING','detail':'Channel and hourly activity are included when available.'})
    for s in slides:
        if s.get('type') == 'breakdown' and not s.get('data'):
            checks.append({'check':'Breakdown slide has data','status':'FAIL','detail':s.get('title','Unnamed')})
    return pd.DataFrame(checks)

def _materiality(df: pd.DataFrame) -> float:
    if not isinstance(df, pd.DataFrame) or df.empty or 'share_pct' not in df.columns:
        return 0.0
    try:
        return float(df.iloc[0]['share_pct'])
    except Exception:
        return 0.0


def _audience_weights(audience: str, team: str) -> dict[str, int]:
    text = f"{audience} {team}".lower()
    weights = {'cases': 2, 'coverage': 1, 'resolution': 1, 'services': 1,
               'channel': 1, 'location': 1, 'priority': 1, 'quality': 1}
    if 'executive' in text or 'management' in text:
        weights.update({'cases': 4, 'resolution': 3, 'coverage': 3, 'priority': 3, 'quality': 2})
    if 'operations' in text:
        weights.update({'cases': 4, 'coverage': 4, 'channel': 3, 'services': 3, 'quality': 3})
    if 'entity' in text:
        weights.update({'resolution': 4, 'services': 3, 'priority': 3, 'quality': 3})
    if 'analyst' in text:
        weights.update({'cases': 3, 'coverage': 3, 'resolution': 3, 'services': 3, 'channel': 3, 'quality': 3})
    return weights



def _breakdown_insight(data, label='segment') -> str:
    if not data:
        return 'No usable data was available for this view.'
    try:
        rows=sorted(data, key=lambda r: float(r.get('cases',0) or 0), reverse=True)
        top=rows[0]; total=sum(float(r.get('cases',0) or 0) for r in rows)
        n=int(float(top.get('cases',0) or 0)); share=(n/total*100) if total else 0
        name=str(top.get('value','')).strip() or 'The leading segment'
        if len(rows)>1:
            second=str(rows[1].get('value','')).strip() or 'the next segment'
            return f"{name} leads this {label} with {n:,} cases ({share:.1f}%). The next segment is {second}; use this view to focus attention where activity is concentrated, not to infer cause."
        return f"{name} accounts for {n:,} cases ({share:.1f}%) in the selected period. This identifies the main concentration of activity; it does not by itself indicate a performance failure or root cause."
    except Exception:
        return 'The chart shows the largest observed segments for the selected period. Use the concentration as a prioritisation signal, not a causal conclusion.'


def _coverage_insight(evidence, summary, represented_override=None) -> str:
    total=summary.get('total_wards')
    represented=evidence.get('distinct_wards') if represented_override is None else represented_override
    if represented is None or not total:
        return 'Ward representation is shown only where an official ward benchmark is available. Unrepresented wards should be treated as a follow-up queue, not as zero demand.'
    pct=float(represented)/float(total)*100 if total else 0
    missing=max(int(total)-int(represented),0)
    if pct >= 100:
        return f"All {int(total):,} configured wards are represented in the evidence. Geographic coverage is complete for the selected period."
    if pct == 0:
        return f"No configured wards are represented in the selected period. All {int(total):,} wards remain a coverage gap and should move to the follow-up queue."
    return f"{int(represented):,} of {int(total):,} configured wards are represented ({pct:.1f}%), leaving {missing:,} unrepresented. Prioritise the uncovered wards before treating the period as geographically representative."


def _channel_time_insight(channel, hourly) -> str:
    parts=[]
    if channel:
        top=max(channel,key=lambda r: float(r.get('cases',0) or 0)); total=sum(float(r.get('cases',0) or 0) for r in channel)
        share=(float(top.get('cases',0) or 0)/total*100) if total else 0
        parts.append(f"{top.get('value','Leading channel')} carries {int(float(top.get('cases',0) or 0)):,} cases ({share:.1f}%)")
    if hourly:
        peak=max(hourly,key=lambda r: float(r.get('cases',0) or 0))
        parts.append(f"peak activity is {int(float(peak.get('cases',0) or 0)):,} cases at {int(peak.get('hour',0)):02d}:00")
    if not parts: return 'No channel or hourly evidence is available.'
    return '. '.join(parts)+'. Use these patterns to review channel capacity and timing; they are activity signals, not proof of service quality.'


def design_report(
    report_plan: dict[str, Any], analysis: dict[str, Any], intelligence: dict[str, Any],
    audience_view: dict[str, Any], period: Any, period_evidence: dict[str, Any] | None = None,
    period_summary: dict[str, Any] | None = None, voc_analysis: dict[str, Any] | None = None,
    analytical_intelligence: dict[str, Any] | None = None,
    decision_intelligence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """V3.8: use a mandatory core framework for daily operational reports.

    Intelligence decides emphasis, not whether an operationally essential section
    disappears. Optional analytical sections are added only when evidence exists.
    """
    evidence = period_evidence or build_period_evidence(analysis, period)
    sections = report_plan.get('sections', [])
    audience = report_plan.get('audience', '')
    team = report_plan.get('requesting_team', '')
    explicit = set(report_plan.get('explicit_focus', []) or [])
    ptype = getattr(period, 'period_type', 'Daily')
    analysis_mode = report_plan.get('analysis_mode', 'Normal Analysis')
    maturity_plan = report_plan.get('maturity_plan', {}) or {}
    extreme = report_plan.get('extreme_analysis', {}) or {}
    slides: list[dict[str, Any]] = []
    slides.append({'type':'cover','title':f"{report_plan.get('department','Report')} Operations & Analytics Report",
                   'subtitle':report_plan.get('period_label','Selected reporting period')})

    ai = analytical_intelligence or {}; di = decision_intelligence or {}
    ai_findings = ai.get('findings')
    if isinstance(ai_findings, pd.DataFrame) and not ai_findings.empty:
        findings = ai_findings.head(8).to_dict('records')
        ai_recs = ai.get('recommendations')
        actions = ai_recs.head(8).to_dict('records') if isinstance(ai_recs,pd.DataFrame) and not ai_recs.empty else _period_actions(findings,evidence)
    else:
        findings = _period_findings(evidence, analysis, period_summary)
        actions = _period_actions(findings, evidence)
    governed = di.get('actions')
    if isinstance(governed,pd.DataFrame) and not governed.empty: actions = governed.head(8).to_dict('records')
    if ptype == 'Daily':
        sd = (analysis.get('dates',{}) or {}).get('selected_day',{}) or {}
        daily_findings=[]
        daily_findings.append({'id':'DAY-001','finding':f"{int(sd.get('cases', evidence.get('case_count',0)) or 0):,} cases were logged on the selected reporting date.", 'evidence_ref':'DAILY-CASES'})
        if evidence.get('distinct_wards') is not None:
            daily_findings.append({'id':'DAY-002','finding':f"{int(evidence.get('distinct_wards')):,} distinct wards were represented on the selected reporting date; {int(sd.get('new_wards',0) or 0):,} were new to the reporting week.", 'evidence_ref':'DAILY-WARDS'})
        if isinstance(sd.get('running_wards'),(int,float)):
            daily_findings.append({'id':'DAY-003','finding':f"Reporting-week running coverage is {int(sd.get('running_wards')):,} wards, with {int(sd.get('still_needed',0) or 0):,} still needed against the configured benchmark where available.", 'evidence_ref':'DAILY-RUNNING'})
        if not evidence.get('channel',pd.DataFrame()).empty:
            r=evidence['channel'].iloc[0]; daily_findings.append({'id':'DAY-004','finding':f"{r['value']} was the leading intake channel with {int(r['cases']):,} cases ({float(r['share_pct']):.1f}%).", 'evidence_ref':'DAILY-CHANNEL'})
        hourly=(analysis.get('dates',{}) or {}).get('by_hour',pd.DataFrame())
        if isinstance(hourly,pd.DataFrame) and not hourly.empty:
            r=hourly.loc[hourly['cases'].idxmax()]; daily_findings.append({'id':'DAY-005','finding':f"Peak activity occurred at {int(r['hour']):02d}:00 with {int(r['cases']):,} cases.", 'evidence_ref':'DAILY-HOUR'})
        findings=daily_findings
    slides.append({'type':'executive_summary','title':'Executive Summary','purpose':'Decision view','findings':findings[:5],'comparison':period_summary or {}})

    # Daily Operations: mandatory core. The core is evidence-driven; unavailable
    # metrics become explicit "not available" items rather than fabricated values.
    if ptype == 'Daily':
        sd = (analysis.get('dates',{}) or {}).get('selected_day',{}) or {}
        summary = analysis.get('summary',{}) or {}
        slides.append({'type':'daily_snapshot','title':'Daily Operational Snapshot',
                       'metrics':[
                           ('Cases logged', sd.get('cases', evidence.get('case_count',0))),
                           ('Daily wards', evidence.get('distinct_wards', sd.get('daily_wards', 'Not available'))),
                           ('New wards', sd.get('new_wards', 'Not available')),
                           ('Running wards', sd.get('running_wards','Not available')),
                           ('Still needed', sd.get('still_needed','Not available')),
                           ('Coverage', f"{sd.get('coverage_pct'):.1f}%" if isinstance(sd.get('coverage_pct'),(int,float)) else 'Not available'),
                       ],
                       'pace': sd.get('suggested_new_wards_per_remaining_day'),
                       'remaining_days': sd.get('remaining_workdays_in_week')})
        # Coverage is mandatory when a ward field/master exists.
        if evidence.get('distinct_wards') is not None:
            slides.append({'type':'coverage','title':'Ward & Geographic Coverage','value':sd.get('running_wards',evidence.get('distinct_wards')),
                           'total':summary.get('total_wards'),'corridor':analysis.get('corridor_coverage',pd.DataFrame()).to_dict('records') if isinstance(analysis.get('corridor_coverage'),pd.DataFrame) else [],
                           'cca':analysis.get('cca_coverage',pd.DataFrame()).to_dict('records') if isinstance(analysis.get('cca_coverage'),pd.DataFrame) else [],
                           'missing': summary.get('missing_wards'), 'insight': _coverage_insight(evidence, summary, sd.get('running_wards', evidence.get('distinct_wards')))})
        # Channel + hourly activity are one mandatory daily operational view.
        if not evidence.get('channel',pd.DataFrame()).empty or not (analysis.get('dates',{}) or {}).get('by_hour',pd.DataFrame()).empty:
            slides.append({'type':'channel_time','title':'Channel & Hourly Activity',
                           'channel':evidence.get('channel',pd.DataFrame()).to_dict('records'),
                           'hourly':(analysis.get('dates',{}) or {}).get('by_hour',pd.DataFrame()).to_dict('records'), 'insight': _channel_time_insight(evidence.get('channel',pd.DataFrame()).to_dict('records'), (analysis.get('dates',{}) or {}).get('by_hour',pd.DataFrame()).to_dict('records'))})
        if not evidence.get('status',pd.DataFrame()).empty:
            slides.append({'type':'breakdown','chart_type':'bar','title':'Case Status','subtitle':'Daily status mix','data':evidence.get('status').to_dict('records'), 'insight': _breakdown_insight(evidence.get('status').to_dict('records'),'status')})
        if not evidence.get('category1',pd.DataFrame()).empty:
            slides.append({'type':'breakdown','chart_type':'bar','title':'Service Demand','subtitle':'Daily Case Category 1','data':evidence.get('category1').to_dict('records'), 'insight': _breakdown_insight(evidence.get('category1').to_dict('records'),'service category')})
        if not evidence.get('city',pd.DataFrame()).empty:
            slides.append({'type':'breakdown','chart_type':'bar','title':'Cases by Location','subtitle':'Daily location mix','data':evidence.get('city').to_dict('records'), 'insight': _breakdown_insight(evidence.get('city').to_dict('records'),'location')})
        if not evidence.get('priority',pd.DataFrame()).empty:
            slides.append({'type':'breakdown','chart_type':'bar','title':'Priority Mix','subtitle':'Daily priority mix','data':evidence.get('priority').to_dict('records'), 'insight': _breakdown_insight(evidence.get('priority').to_dict('records'),'priority segment')})
        q=analysis.get('quality',pd.DataFrame())
        if isinstance(q,pd.DataFrame) and not q.empty:
            slides.append({'type':'quality','title':'Data Quality & Limitations','data':q.head(8).to_dict('records')})
        if voc_analysis and voc_analysis.get('available'):
            slides.append({'type':'voc','title':'Voice of Citizen','data':voc_analysis})
    else:
        daily=evidence.get('daily',pd.DataFrame())
        if isinstance(daily,pd.DataFrame) and len(daily)>=2:
            slides.append({'type':'trend','title':'Performance Trend','subtitle':f"{ptype} case activity",'data':daily.to_dict('records'),'comparison':period_summary or {}})
        else:
            slides.append({'type':'kpi_snapshot','title':'Period Performance Snapshot','metrics':[
                ('Period cases',f"{int(evidence.get('case_count',0)):,}"),
                ('Distinct wards',str(evidence.get('distinct_wards')) if evidence.get('distinct_wards') is not None else 'Not available'),
                ('Comparison',(f"{period_summary.get('change_pct'):+.1f}%" if period_summary and isinstance(period_summary.get('change_pct'),(int,float)) else 'Not available'))]})
        # Non-daily periods retain intelligent optional selection.
        candidates=[]; section_map={'Geographic / Coverage Position':('coverage','coverage'),'Case Workflow / Resolution Position':('resolution','status'),'Service and Demand Mix':('services','category1'),'Channel and Time Activity':('channel','channel'),'Location / Entity Performance':('location','city'),'Priority / Risk Position':('priority','priority'),'Voice of Citizen':('customer','voc'),'Data Quality and Limitations':('quality','quality')}
        weights=_audience_weights(audience,team); focus_rank={f:i for i,f in enumerate(report_plan.get('planning_focus',[]) or [])}
        for sec in sections:
            title=sec.get('title','')
            if title not in section_map or not _section_available(title,evidence,analysis): continue
            focus,key=section_map[title]
            if title=='Voice of Citizen':
                if not(voc_analysis and voc_analysis.get('available')): continue
                mat=50.0
            elif key=='quality':
                q=analysis.get('quality',pd.DataFrame()); mat=100.0 if isinstance(q,pd.DataFrame) and not q.empty else 0.0
            else:
                df=evidence.get(key,pd.DataFrame()); mat=_materiality(df)
                if isinstance(df,pd.DataFrame) and len(df)<2 and key!='city': mat*=0.35
            score=weights.get(focus,1)*10+max(0,20-focus_rank.get(focus,10))+min(mat,100)*0.20
            if focus in explicit: score+=25
            candidates.append((score,title,focus,key,mat))
        candidates.sort(reverse=True); chosen=[]; used=[]
        max_analytic=4 if ptype in {'Daily','Weekly'} else 5
        for item in candidates:
            if item[2] in used: continue
            chosen.append(item); used.append(item[2])
            if len(chosen)>=max_analytic: break
        for _,title,focus,key,mat in chosen:
            if title=='Geographic / Coverage Position': slides.append({'type':'coverage','title':title,'value':evidence.get('distinct_wards'),'total':analysis.get('summary',{}).get('total_wards'),'corridor':[],'cca':[], 'insight': _coverage_insight(evidence, analysis.get('summary',{}))})
            elif title=='Case Workflow / Resolution Position': slides.append({'type':'breakdown','chart_type':'bar','title':'Case Status','subtitle':'Period status mix','data':evidence.get('status',pd.DataFrame()).to_dict('records'), 'insight': _breakdown_insight(evidence.get('status',pd.DataFrame()).to_dict('records'),'status')})
            elif title=='Service and Demand Mix': slides.append({'type':'breakdown','chart_type':'bar','title':'Service Demand','subtitle':'Leading service categories','data':evidence.get('category1',pd.DataFrame()).to_dict('records'), 'insight': _breakdown_insight(evidence.get('category1',pd.DataFrame()).to_dict('records'),'service category')})
            elif title=='Channel and Time Activity': slides.append({'type':'channel_time','title':title,'channel':evidence.get('channel',pd.DataFrame()).to_dict('records'),'hourly':(analysis.get('dates',{}) or {}).get('by_hour',pd.DataFrame()).to_dict('records'), 'insight': _channel_time_insight(evidence.get('channel',pd.DataFrame()).to_dict('records'), (analysis.get('dates',{}) or {}).get('by_hour',pd.DataFrame()).to_dict('records'))})
            elif title=='Location / Entity Performance': slides.append({'type':'breakdown','chart_type':'bar','title':'Cases by Location','subtitle':'Period location mix','data':evidence.get('city',pd.DataFrame()).to_dict('records'), 'insight': _breakdown_insight(evidence.get('city',pd.DataFrame()).to_dict('records'),'location')})
            elif title=='Priority / Risk Position': slides.append({'type':'breakdown','chart_type':'bar','title':'Priority Mix','subtitle':'Period priority mix','data':evidence.get('priority',pd.DataFrame()).to_dict('records'), 'insight': _breakdown_insight(evidence.get('priority',pd.DataFrame()).to_dict('records'),'priority segment')})
            elif title=='Voice of Citizen': slides.append({'type':'voc','title':title,'data':voc_analysis})
            elif title=='Data Quality and Limitations':
                q=analysis.get('quality',pd.DataFrame()); slides.append({'type':'quality','title':title,'data':q.head(8).to_dict('records')})

    if analysis_mode == 'Extreme Analysis':
        ex = ai.get('extreme_analysis', {}) or {}
        pareto = ex.get('pareto', pd.DataFrame())
        fishbone = ex.get('fishbone', pd.DataFrame())
        five = ex.get('five_whys', pd.DataFrame())
        pred = ex.get('predictive', {}) or {}
        pred_series = ex.get('predictive_series', pd.DataFrame())
        if isinstance(pareto, pd.DataFrame) and not pareto.empty:
            slides.append({'type':'extreme_diagnostic_pareto','title':'Extreme Analysis — Pareto Priority Screen','subtitle':f'Largest concentration segments — {ex.get("pareto_dimension", "selected dimension")}', 'pareto':pareto.to_dict('records')})
            slides.append({'type':'extreme_diagnostic_framework','title':'Extreme Analysis — Diagnostic Investigation','subtitle':'Fishbone cause framework + Five Whys prompts','fishbone':fishbone.to_dict('records') if isinstance(fishbone,pd.DataFrame) else [],'five_whys':five.to_dict('records') if isinstance(five,pd.DataFrame) else []})
        if pred.get('available'):
            slides.append({'type':'extreme_predictive','title':'Extreme Analysis — Predictive Outlook','subtitle':'Evidence-gated historical trend screen','predictive':pred,'series':pred_series.to_dict('records') if isinstance(pred_series,pd.DataFrame) else []})
        slides.append({'type':'extreme_optimisation','title':'Extreme Analysis — Optimisation & Control Review','subtitle':'Corrective / preventive action candidates','findings':ex.get('findings',pd.DataFrame()).to_dict('records') if isinstance(ex.get('findings'),pd.DataFrame) else [],'gaps':maturity_plan.get('evidence_gaps',[])})

    slides.append({'type':'actions','title':'Actions and Management Decisions','data':actions[:6]})
    slides.append({'type':'method','title':'Evidence and Method Note','items':report_plan.get('addendum_items',[])[:8]})
    return {
        'version':'1.3','department':report_plan.get('department'),'requesting_team':team,'entity_context':report_plan.get('entity_context',{}),
        'audience':audience,'period_type':ptype,'period_label':getattr(period,'label','Selected reporting period'),'slides':slides,
        'period_evidence':evidence,'period_findings':findings,'period_actions':actions,'analytical_intelligence':ai,'decision_intelligence':di,'extreme_analysis':extreme,'analysis_mode':analysis_mode,'maturity_plan':maturity_plan,
        'selection_log':[],'rules':{'no_fabrication':True,'main_report_concise':True,'detailed_evidence_in_addendum':True,
        'mandatory_daily_operations_framework':ptype=='Daily','layout_safe_text_v3_8':True,'no_overlapping_text_v3_8':True,
        'materiality_driven_selection':ptype!='Daily','audience_driven_selection':True,'avoid_single_point_trends':True,
        'analytical_intelligence_v3_4':bool(ai),'business_implication_required':True,'decision_action_governance_v3_6':bool(di),'actions_require_evidence':True,'analysis_mode':analysis_mode,'extreme_analysis_evidence_gated':analysis_mode=='Extreme Analysis','analytical_maturity_v3_9':True}
    }
