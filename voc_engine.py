from __future__ import annotations
import pandas as pd
import numpy as np


def _col(df, terms):
    if df is None: return None
    for c in df.columns:
        s = str(c).replace('\xa0',' ').strip().lower()
        if all(t in s for t in terms): return c
    return None


def _pct(n, d):
    return round(float(n) / float(d) * 100, 1) if d else None


def _score_group(v, metric):
    s = v.astype('string').str.strip().str.lower()
    if metric == 'satisfaction':
        return s.isin(['very satisfied','satisfied']).sum(), s.notna().sum()
    if metric == 'effort':
        return s.isin(['very easy','easy']).sum(), s.notna().sum()
    return None, s.notna().sum()


def _metric_detail(df, service_col, metric_cols):
    if df is None or df.empty or not service_col: return pd.DataFrame()
    rows=[]
    for service, g in df.groupby(service_col, dropna=False):
        row={'Main Service': str(service) if pd.notna(service) else 'Unknown', 'Responses': len(g)}
        for key,col in metric_cols.items():
            if not col: continue
            x=g[col].astype('string').str.strip().str.lower()
            if key=='happiness':
                valid=x.notna() & x.ne(''); row['Happiness %']=_pct(x.eq('yes').sum(), valid.sum())
            elif key=='satisfaction':
                pos=x.isin(['very satisfied','satisfied']); row['Satisfaction top-two %']=_pct(pos.sum(), x.notna().sum())
            elif key=='effort':
                pos=x.isin(['very easy','easy']); row['Effort top-two %']=_pct(pos.sum(), x.notna().sum())
            elif key=='nps':
                num=pd.to_numeric(g[col], errors='coerce'); row['Promote score avg']=round(float(num.mean()),2) if num.notna().any() else None
                row['Promoter %']=_pct((num>=9).sum(), num.notna().sum()); row['Detractor %']=_pct((num<=6).sum(), num.notna().sum())
        rows.append(row)
    return pd.DataFrame(rows).sort_values('Responses', ascending=False).reset_index(drop=True)


def analyze_voc(main_df: pd.DataFrame | None, happiness_df: pd.DataFrame | None = None, detail_df: pd.DataFrame | None = None) -> dict:
    """Analyse a three-layer VoC package: master survey, happiness detail, and additional metric detail.
    The engine never invents a join. It uses Case Ref when present and reports unmatched rows explicitly.
    """
    if main_df is None or main_df.empty:
        return {'available': False, 'responses': 0, 'sources': {}}
    df=main_df.copy()
    cols=list(df.columns)
    case=_col(df,['case','ref'])
    submit=next((c for c in cols if str(c).strip().lower().startswith('submit date')),None)
    service=next((c for c in cols if str(c).strip().lower()=='main service'),None) or _col(df,['main','service'])
    subservice=_col(df,['sub','service'])
    topic=_col(df,['service','topic'])
    resolution=_col(df,['happy','resolved'])
    satisfaction=_col(df,['how satisfied'])
    ease=_col(df,['how easy'])
    promote=_col(df,['how likely','promote'])
    out={'available':True,'responses':len(df),'date_column':submit,
         'columns':{'case_ref':case,'service':service,'sub_service':subservice,'topic':topic,'resolution':resolution,'satisfaction':satisfaction,'ease':ease,'promote':promote},
         'sources':{'master': 'main survey', 'happiness_detail': bool(happiness_df is not None and not happiness_df.empty), 'metric_detail': bool(detail_df is not None and not detail_df.empty)}}
    if case:
        out['unique_case_refs']=int(df[case].astype('string').str.strip().replace('',pd.NA).dropna().nunique())
    if submit:
        dt=pd.to_datetime(df[submit], errors='coerce'); out['min_date']=dt.min(); out['max_date']=dt.max()
    # Main survey metrics
    if resolution:
        x=df[resolution].astype('string').str.strip().str.lower(); valid=x.notna() & x.ne('')
        out['happiness']=f"{_pct(x.eq('yes').sum(),valid.sum()):.1f}%" if valid.any() else 'Not calculated'
        out['resolved']=int(x.eq('yes').sum())
        out['happiness_denominator']=int(valid.sum())
    else: out['happiness']='Not calculated'; out['resolved']='Not calculated'
    if satisfaction:
        n=df[satisfaction].notna().sum(); out['satisfaction_top_two']=f"{_pct(df[satisfaction].astype('string').str.lower().isin(['very satisfied','satisfied']).sum(),n):.1f}%" if n else 'Not calculated'
    else: out['satisfaction_top_two']='Not calculated'
    if ease:
        n=df[ease].notna().sum(); out['effort_top_two']=f"{_pct(df[ease].astype('string').str.lower().isin(['very easy','easy']).sum(),n):.1f}%" if n else 'Not calculated'
    else: out['effort_top_two']='Not calculated'
    if promote:
        num=pd.to_numeric(df[promote],errors='coerce')
        if num.notna().sum()==0:
            ps=df[promote].astype('string').str.strip().str.lower()
            mapped=ps.map({'extremely likely':10,'very likely':10,'likely':8,'neutral':7,'unlikely':5,'very unlikely':2,'not at all likely':0})
            num=mapped
        n=num.notna().sum(); out['promote_avg']=round(float(num.mean()),2) if n else None; out['nps_grouped']=round((_pct((num>=9).sum(),n) or 0)-(_pct((num<=6).sum(),n) or 0),1) if n else None
    else: out['promote_avg']=None; out['nps_grouped']=None
    required=[c for c in [resolution,satisfaction,ease,promote] if c]
    out['survey_ready']=f"{int(df[required].notna().all(axis=1).sum())}/{len(df)}" if required else 'Not calculated'

    # Master service and topic distributions
    if service:
        svc=df[service].fillna('Unknown').astype(str).value_counts().rename_axis('Main Service').reset_index(name='Responses')
        svc['Share %']=(svc['Responses']/len(df)*100).round(1); out['service_summary']=svc
        out['top_service']=str(svc.iloc[0]['Main Service']) if not svc.empty else None
    if topic:
        top=df[topic].fillna('Unknown').astype(str).value_counts().rename_axis('Service Topic').reset_index(name='Responses'); top['Share %']=(top['Responses']/len(df)*100).round(1); out['topic_summary']=top.head(15)
    if service:
        out['metric_by_service']=_metric_detail(df,service,{'happiness':resolution,'satisfaction':satisfaction,'effort':ease,'nps':promote})

    # Happiness detail source
    if happiness_df is not None and not happiness_df.empty:
        h=happiness_df.copy(); hc=_col(h,['case','ref']); ht=_col(h,['service','topic']); hv=_col(h,['happy','resolution','yes','no']) or _col(h,['happy','resolution'])
        hr=_col(h,['reason','why'])
        out['happiness_detail_rows']=len(h); out['happiness_detail_unique_cases']=int(h[hc].astype('string').str.strip().replace('',pd.NA).dropna().nunique()) if hc else None
        if hv:
            hx=h[hv].astype('string').str.strip().str.lower(); valid=hx.notna()&hx.ne(''); out['happiness_detail_pct']=_pct(hx.eq('yes').sum(),valid.sum()) if valid.any() else None
            out['happiness_detail_positive']=int(hx.eq('yes').sum()); out['happiness_detail_negative']=int(hx.eq('no').sum())
        if ht:
            out['happiness_by_topic']=h[ht].fillna('Unknown').astype(str).groupby(lambda i: i).size() if False else h[ht].fillna('Unknown').astype(str).value_counts().rename_axis('Service Topic').reset_index(name='Responses')
        if hr:
            hh=h[[c for c in [hc,ht,hv,hr] if c]].copy(); hh.columns=['Case Ref' if c==hc else 'Service Topic' if c==ht else 'Resolution' if c==hv else 'Reason' for c in hh.columns]
            out['happiness_detail']=hh
        if hc and case:
            a=set(df[case].astype('string').str.strip().dropna()); b=set(h[hc].astype('string').str.strip().dropna()); out['happiness_unmatched_main']=len(b-a); out['happiness_missing_detail']=len(a-b)

    # Additional metric detail source: effort, satisfaction, promote + reasons
    if detail_df is not None and not detail_df.empty:
        d=detail_df.copy(); dc=_col(d,['case','ref']); ds=next((c for c in d.columns if str(c).strip().lower()=='main services'),None) or _col(d,['main','service']); de=_col(d,['effort','score']); der=_col(d,['detail','reasons','effort']); dsa=_col(d,['satisfaction','score']); dsar=_col(d,['detail','reason','satisfaction']); dp=_col(d,['promote','score']); dpr=_col(d,['detail','reason','promoter'])
        out['metric_detail_rows']=len(d); out['metric_detail_unique_cases']=int(d[dc].astype('string').str.strip().replace('',pd.NA).dropna().nunique()) if dc else None
        out['metric_detail_by_service']=_metric_detail(d,ds,{'effort':de,'satisfaction':dsa,'nps':dp}) if ds else pd.DataFrame()
        out['metric_detail']=d
        if dc and case:
            a=set(df[case].astype('string').str.strip().dropna()); b=set(d[dc].astype('string').str.strip().dropna()); out['metric_unmatched_main']=len(b-a); out['metric_missing_detail']=len(a-b)
        for key,col in [('effort_score',de),('satisfaction_score',dsa),('promote_score',dp)]:
            if col: out[key]=pd.to_numeric(d[col],errors='coerce').mean()
        reason_frames=[]
        for metric,col in [('Effort',der),('Satisfaction',dsar),('Promoter',dpr)]:
            if col:
                keep=[c for c in [dc,ds,col] if c]; q=d[keep].copy(); q['Metric']=metric;
                if dc: q=q.rename(columns={dc:'Case Ref'})
                else: q['Case Ref']='Not supplied in detail source'
                if ds: q=q.rename(columns={ds:'Main Service'})
                else: q['Main Service']='Not supplied in detail source'
                q=q.rename(columns={col:'Detailed Reason'}); reason_frames.append(q[['Case Ref','Main Service','Metric','Detailed Reason']])
        if reason_frames: out['metric_reason_detail']=pd.concat(reason_frames,ignore_index=True)

    # Follow-up queue from happiness detail: negative resolution responses
    if isinstance(out.get('happiness_detail'),pd.DataFrame):
        q=out['happiness_detail'].copy(); out['negative_queue']=q[q.get('Resolution','').astype('string').str.lower().eq('no')].copy()
    else: out['negative_queue']=pd.DataFrame()
    out['available_layers']=sum([1, bool(happiness_df is not None and not happiness_df.empty), bool(detail_df is not None and not detail_df.empty)])
    return out
