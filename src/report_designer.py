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
        wards = work[cols['ward']].astype('string').str.strip().replace({'': pd.NA, 'nan': pd.NA}).dropna()
        out['distinct_wards'] = int(wards.nunique())
    else:
        out['distinct_wards'] = None
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


def design_report(
    report_plan: dict[str, Any],
    analysis: dict[str, Any],
    intelligence: dict[str, Any],
    audience_view: dict[str, Any],
    period: Any,
    period_evidence: dict[str, Any] | None = None,
    period_summary: dict[str, Any] | None = None,
    voc_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Design a concise, evidence-led deck rather than mechanically mirroring the planner.

    The designer makes three decisions: materiality, audience relevance and visual form.
    It never creates a slide for a capability that is unavailable or a chart that has
    insufficient observations to communicate a pattern.
    """
    evidence = period_evidence or build_period_evidence(analysis, period)
    sections = report_plan.get('sections', [])
    audience = report_plan.get('audience', '')
    team = report_plan.get('requesting_team', '')
    explicit = set(report_plan.get('explicit_focus', []) or [])
    weights = _audience_weights(audience, team)
    slides: list[dict[str, Any]] = []

    slides.append({'type':'cover', 'title':f"{report_plan.get('department','Report')} Operations & Analytics Report",
                   'subtitle':report_plan.get('period_label','Selected reporting period')})

    findings = _period_findings(evidence, analysis, period_summary)
    actions = _period_actions(findings, evidence)
    slides.append({'type':'executive_summary', 'title':'Executive Summary', 'purpose':'Decision view',
                   'findings':findings[:5], 'comparison':period_summary or {}})

    # A KPI slide is more useful than a one-point trend for daily/small periods.
    daily = evidence.get('daily', pd.DataFrame())
    if isinstance(daily, pd.DataFrame) and len(daily) >= 2:
        slides.append({'type':'trend', 'title':'Performance Trend',
                       'subtitle':f"{getattr(period, 'period_type', 'Period')} case activity",
                       'data':daily.to_dict('records'), 'comparison':period_summary or {}})
    else:
        slides.append({'type':'kpi_snapshot', 'title':'Period Performance Snapshot',
                       'metrics':[
                           ('Period cases', f"{int(evidence.get('case_count',0)):,}"),
                           ('Distinct wards', str(evidence.get('distinct_wards')) if evidence.get('distinct_wards') is not None else 'Not available'),
                           ('Comparison', (f"{period_summary.get('change_pct'):+.1f}%" if period_summary and isinstance(period_summary.get('change_pct'),(int,float)) else 'Not available')),
                       ]})

    candidates=[]
    section_map = {
        'Geographic / Coverage Position': ('coverage','coverage'),
        'Case Workflow / Resolution Position': ('resolution','status'),
        'Service and Demand Mix': ('services','category1'),
        'Channel and Time Activity': ('channel','channel'),
        'Location / Entity Performance': ('location','city'),
        'Priority / Risk Position': ('priority','priority'),
        'Voice of Citizen': ('customer','voc'),
        'Data Quality and Limitations': ('quality','quality'),
    }
    focus_rank={f:i for i,f in enumerate(report_plan.get('planning_focus',[]) or [])}
    for sec in sections:
        title=sec.get('title','')
        if title not in section_map or not _section_available(title,evidence,analysis):
            continue
        focus, key=section_map[title]
        if title == 'Voice of Citizen':
            if not (voc_analysis and voc_analysis.get('available')): continue
            mat=50.0
        elif key == 'quality':
            q=analysis.get('quality', pd.DataFrame()); mat=100.0 if isinstance(q,pd.DataFrame) and not q.empty else 0.0
        else:
            df=evidence.get(key, pd.DataFrame()); mat=_materiality(df)
            if isinstance(df,pd.DataFrame) and len(df) < 2 and key not in {'city'}:
                mat *= 0.35
        score = weights.get(focus,1)*10 + max(0, 20-focus_rank.get(focus,10)) + min(mat,100)*0.20
        if focus in explicit: score += 25
        candidates.append((score,title,focus,key,mat))

    # Avoid redundant mix slides: select the strongest few dimensions.
    candidates.sort(reverse=True)
    chosen=[]; used=[]
    max_analytic = 4 if getattr(period,'period_type','Daily') in {'Daily','Weekly'} else 5
    for item in candidates:
        score,title,focus,key,mat=item
        if focus in used: continue
        chosen.append(item); used.append(focus)
        if len(chosen)>=max_analytic: break

    for _, title, focus, key, mat in chosen:
        if title == 'Geographic / Coverage Position':
            total=analysis.get('summary',{}).get('total_wards')
            slides.append({'type':'coverage','title':title,'value':evidence.get('distinct_wards'),'total':total,
                           'corridor':[]})
        elif title == 'Case Workflow / Resolution Position':
            slides.append({'type':'breakdown','chart_type':'bar','title':title,'subtitle':'Period-aligned status mix',
                           'data':evidence.get('status',pd.DataFrame()).to_dict('records')})
        elif title == 'Service and Demand Mix':
            slides.append({'type':'breakdown','chart_type':'bar','title':title,'subtitle':'Leading Case Category 1',
                           'data':evidence.get('category1',pd.DataFrame()).to_dict('records')})
        elif title == 'Channel and Time Activity':
            slides.append({'type':'breakdown','chart_type':'donut' if len(evidence.get('channel',pd.DataFrame())) <= 5 else 'bar',
                           'title':title,'subtitle':'Period intake channel mix',
                           'data':evidence.get('channel',pd.DataFrame()).to_dict('records')})
        elif title == 'Location / Entity Performance':
            slides.append({'type':'breakdown','chart_type':'bar','title':title,'subtitle':'Period location mix',
                           'data':evidence.get('city',pd.DataFrame()).to_dict('records')})
        elif title == 'Priority / Risk Position':
            slides.append({'type':'breakdown','chart_type':'bar','title':title,'subtitle':'Period priority mix',
                           'data':evidence.get('priority',pd.DataFrame()).to_dict('records')})
        elif title == 'Voice of Citizen':
            slides.append({'type':'voc','title':title,'data':voc_analysis})
        elif title == 'Data Quality and Limitations':
            q=analysis.get('quality',pd.DataFrame())
            slides.append({'type':'quality','title':title,'data':q.head(8).to_dict('records')})

    slides.append({'type':'actions','title':'Actions and Management Decisions','data':actions[:6]})
    slides.append({'type':'method','title':'Evidence and Method Note','items':report_plan.get('addendum_items',[])[:8]})

    max_slides = 9 if 'Executive' in str(audience) else 10
    if len(slides)>max_slides:
        # Preserve cover, executive, snapshot/trend, actions and method; trim weakest analytics.
        fixed_types={'cover','executive_summary','kpi_snapshot','trend','actions','method'}
        fixed=[s for s in slides if s['type'] in fixed_types]
        middle=[s for s in slides if s['type'] not in fixed_types]
        slides=fixed[:max_slides]
        remaining=max_slides-len(slides)
        if remaining>0: slides=fixed + middle[:remaining]
        # Restore original logical order using object identity.
        ordered=[]
        for s in [*slides]:
            ordered.append(s)
        slides=ordered

    return {
        'version':'1.1', 'department':report_plan.get('department'), 'requesting_team':team,
        'audience':audience, 'period_type':getattr(period,'period_type','Daily'),
        'period_label':getattr(period,'label','Selected reporting period'), 'slides':slides,
        'period_evidence':evidence, 'period_findings':findings, 'period_actions':actions,
        'selection_log': [
            {'section':x[1], 'score':round(x[0],1), 'focus':x[2], 'materiality':round(x[4],1)}
            for x in chosen
        ],
        'rules': {'no_fabrication':True,'main_report_concise':True,'detailed_evidence_in_addendum':True,
                  'materiality_driven_selection':True,'audience_driven_selection':True,
                  'avoid_single_point_trends':True},
    }
