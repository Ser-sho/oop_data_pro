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
    evidence = period_evidence or build_period_evidence(analysis, period)
    sections = report_plan.get('sections', [])
    period_findings = _period_findings(evidence, analysis, period_summary)
    period_actions = _period_actions(period_findings, evidence)
    slides: list[dict[str, Any]] = []
    slides.append({'type':'cover','title':f"{report_plan.get('department','Report')} Operations & Analytics Report",'subtitle':report_plan.get('period_label','Selected reporting period')})

    selected = [s for s in sections if _section_available(s['title'], evidence, analysis)]
    # The executive slide is always first after cover.
    slides.append({'type':'executive_summary','title':'Executive Summary','purpose':'Decision view','findings':period_findings[:5], 'comparison':period_summary or {}})

    for s in selected:
        title = s['title']
        if title == 'Executive Summary':
            continue
        if title == 'Performance and Activity':
            slides.append({'type':'trend','title':'Performance and Activity','data':evidence.get('daily', pd.DataFrame()).to_dict('records'),'comparison':period_summary or {}})
        elif title == 'Geographic / Coverage Position':
            slides.append({'type':'coverage','title':'Geographic / Coverage Position','value':evidence.get('distinct_wards'),'total':analysis.get('summary',{}).get('total_wards'),'corridor':analysis.get('corridor_coverage',pd.DataFrame()).to_dict('records')})
        elif title == 'Case Workflow / Resolution Position':
            slides.append({'type':'breakdown','title':title,'subtitle':'Period-aligned status mix','data':evidence.get('status',pd.DataFrame()).to_dict('records')})
        elif title == 'Service and Demand Mix':
            slides.append({'type':'breakdown','title':title,'subtitle':'Leading Case Category 1','data':evidence.get('category1',pd.DataFrame()).to_dict('records')})
        elif title == 'Channel and Time Activity':
            slides.append({'type':'breakdown','title':title,'subtitle':'Period channel mix','data':evidence.get('channel',pd.DataFrame()).to_dict('records')})
        elif title == 'Location / Entity Performance':
            slides.append({'type':'breakdown','title':title,'subtitle':'Period location mix','data':evidence.get('city',pd.DataFrame()).to_dict('records')})
        elif title == 'Priority / Risk Position':
            slides.append({'type':'breakdown','title':title,'subtitle':'Period priority mix','data':evidence.get('priority',pd.DataFrame()).to_dict('records')})
        elif title == 'Voice of Citizen' and voc_analysis and voc_analysis.get('available'):
            slides.append({'type':'voc','title':title,'data':voc_analysis})
        elif title == 'Data Quality and Limitations':
            q = analysis.get('quality', pd.DataFrame())
            slides.append({'type':'quality','title':title,'data':q.head(8).to_dict('records')})
        elif title == 'Actions and Management Decisions':
            slides.append({'type':'actions','title':title,'data':period_actions[:6]})
        elif title == 'Evidence and Method Note':
            slides.append({'type':'method','title':title,'items':report_plan.get('addendum_items',[])[:8]})

    # Always finish with a concise methodology/evidence slide if the planner did
    # not already add one. Detailed registers remain in the addendum.
    if not any(s['type']=='method' for s in slides):
        slides.append({'type':'method','title':'Evidence and Method Note','items':report_plan.get('addendum_items',[])[:8]})

    # Avoid overlong decks. Automatic design is intentionally management-sized.
    max_slides = 10 if report_plan.get('audience') != 'Executive management' else 8
    if len(slides) > max_slides:
        # Preserve cover, executive, actions and method; drop lower-ranked middle slides first.
        must_types = {'cover','executive_summary','actions','method'}
        kept=[]
        for s in slides:
            if s['type'] in must_types:
                kept.append(s)
        for s in slides:
            if s in kept:
                continue
            if len(kept) >= max_slides:
                break
            kept.append(s)
        # restore logical order from original sequence
        slides = [s for s in slides if s in kept]

    return {
        'version':'1.0',
        'department':report_plan.get('department'),
        'requesting_team':report_plan.get('requesting_team'),
        'audience':report_plan.get('audience'),
        'period_type':getattr(period,'period_type','Daily'),
        'period_label':getattr(period,'label','Selected reporting period'),
        'slides':slides,
        'period_evidence':evidence,
        'period_findings':period_findings,
        'period_actions':period_actions,
        'rules': {
            'no_fabrication': True,
            'main_report_concise': True,
            'detailed_evidence_in_addendum': True,
        },
    }
