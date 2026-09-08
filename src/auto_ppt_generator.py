from __future__ import annotations
from pathlib import Path
from typing import Any
import math
import pandas as pd
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION
from pptx.chart.data import ChartData

NAVY='17324D'; BLUE='0058A8'; GOLD='FFC000'; LIGHT='F3F6FA'; MID='D9E2F3'; DARK='263238'; WHITE='FFFFFF'; RED='C00000'; GREEN='2E7D32'
FONT='Aptos'


def rgb(x): return RGBColor.from_string(x)

def box(slide, x,y,w,h, fill=WHITE, line=MID, radius=True):
    shp=slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid(); shp.fill.fore_color.rgb=rgb(fill)
    shp.line.color.rgb=rgb(line); shp.line.width=Pt(0.7)
    return shp

def text(slide, x,y,w,h, value, size=16, bold=False, color=DARK, align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP):
    tb=slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf=tb.text_frame; tf.clear(); tf.vertical_anchor=valign; tf.word_wrap=True; tf.auto_size=MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    tf.margin_left=Inches(0.02); tf.margin_right=Inches(0.02); tf.margin_top=Inches(0.01); tf.margin_bottom=Inches(0.01)
    p=tf.paragraphs[0]; p.alignment=align
    r=p.add_run(); r.text=str(value); r.font.name=FONT; r.font.size=Pt(size); r.font.bold=bold; r.font.color.rgb=rgb(color)
    return tb

def title_bar(slide, title, subtitle=''):
    text(slide,0.55,0.32,11.7,0.45,title,23,True,NAVY)
    if subtitle: text(slide,0.57,0.80,11.4,0.3,subtitle,9,False,'5C6B78')
    slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.55), Inches(1.16), Inches(11.75), Inches(0.04)).fill.solid()
    slide.shapes[-1].fill.fore_color.rgb=rgb(GOLD); slide.shapes[-1].line.fill.background()

def footer(slide, dept, team, period):
    text(slide,0.55,7.10,8.0,0.22,f"{dept}  •  {team}  •  {period}",7,False,'6B7785')
    text(slide,10.6,7.10,1.7,0.22,"Evidence-led report",7,False,'6B7785',PP_ALIGN.RIGHT)

def add_chart(slide, data, x,y,w,h, title, horizontal=True):
    if not data: return
    cats=[str(r.get('value',''))[:28] for r in data]
    vals=[float(r.get('cases',0) or 0) for r in data]
    cd=ChartData(); cd.categories=cats; cd.add_series('Cases',vals)
    typ=XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
    chart=slide.shapes.add_chart(typ, Inches(x), Inches(y), Inches(w), Inches(h), cd).chart
    chart.has_title=True; chart.chart_title.text_frame.text=title
    chart.chart_title.text_frame.paragraphs[0].runs[0].font.name=FONT; chart.chart_title.text_frame.paragraphs[0].runs[0].font.size=Pt(10); chart.chart_title.text_frame.paragraphs[0].runs[0].font.bold=True; chart.chart_title.text_frame.paragraphs[0].runs[0].font.color.rgb=rgb(NAVY)
    chart.has_legend=False
    ser=chart.series[0]; ser.format.fill.solid(); ser.format.fill.fore_color.rgb=rgb(BLUE); ser.format.line.color.rgb=rgb(BLUE)
    try:
        ser.has_data_labels=True; ser.data_labels.show_value=True; ser.data_labels.font.name=FONT; ser.data_labels.font.size=Pt(7); ser.data_labels.font.color.rgb=rgb(DARK); ser.data_labels.position=XL_LABEL_POSITION.OUTSIDE_END
    except Exception: pass
    try:
        chart.value_axis.minimum_scale=0; chart.value_axis.maximum_scale=max(max(vals+[1])*1.18,1); chart.value_axis.major_gridlines.format.line.color.rgb=rgb(MID)
        chart.value_axis.tick_labels.font.name=FONT; chart.value_axis.tick_labels.font.size=Pt(7)
        chart.category_axis.tick_labels.font.name=FONT; chart.category_axis.tick_labels.font.size=Pt(7)
        if horizontal: chart.category_axis.reverse_order=True
    except Exception: pass
    return chart

def add_line(slide, rows, x,y,w,h):
    if not rows: return
    rows=sorted(rows,key=lambda r:r['date']); cats=[pd.Timestamp(r['date']).strftime('%d %b') for r in rows]; vals=[float(r['cases']) for r in rows]
    cd=ChartData(); cd.categories=cats; cd.add_series('Cases',vals)
    chart=slide.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(x), Inches(y), Inches(w), Inches(h), cd).chart
    chart.has_title=False; chart.has_legend=False
    ser=chart.series[0]; ser.format.line.color.rgb=rgb(BLUE); ser.format.line.width=Pt(2)
    try: ser.marker.size=6
    except Exception: pass
    try:
        chart.value_axis.minimum_scale=0; chart.value_axis.major_gridlines.format.line.color.rgb=rgb(MID); chart.value_axis.tick_labels.font.name=FONT; chart.value_axis.tick_labels.font.size=Pt(7); chart.category_axis.tick_labels.font.name=FONT; chart.category_axis.tick_labels.font.size=Pt(7)
    except Exception: pass
    return chart

def add_kpi(slide,x,y,w,label,value,accent=BLUE):
    box(slide,x,y,w,1.05,WHITE,MID)
    text(slide,x+0.16,y+0.14,w-0.3,0.25,label,8,False,'687783')
    text(slide,x+0.16,y+0.40,w-0.3,0.43,value,20,True,accent)

def add_insight_box(slide, x, y, w, h, insight, title="What the chart means"):
    box(slide,x,y,w,h,LIGHT,LIGHT)
    text(slide,x+0.18,y+0.12,w-0.36,0.24,title,9,True,NAVY)
    text(slide,x+0.18,y+0.40,w-0.36,h-0.50,insight or 'No additional interpretation is available.',9,False,DARK)


def _finding_text(row):
    return str(row.get('finding',''))

def add_donut(slide, data, x, y, w, h):
    if not data: return
    cats=[str(r.get('value',''))[:22] for r in data]
    vals=[float(r.get('cases',0) or 0) for r in data]
    cd=ChartData(); cd.categories=cats; cd.add_series('Cases', vals)
    ch=slide.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, Inches(x), Inches(y), Inches(w), Inches(h), cd).chart
    ch.has_legend=True; ch.legend.position=XL_LEGEND_POSITION.RIGHT
    try:
        ch.legend.font.name=FONT; ch.legend.font.size=Pt(8)
    except Exception: pass
    try:
        ch.plots[0].has_data_labels=True; ch.plots[0].data_labels.show_percentage=True
        ch.plots[0].data_labels.font.name=FONT; ch.plots[0].data_labels.font.size=Pt(8)
    except Exception: pass
    return ch



def generate_auto_powerpoint(out_path: Path, blueprint: dict[str,Any]):
    prs=Presentation(); prs.slide_width=Inches(13.333); prs.slide_height=Inches(7.5)
    blank=prs.slide_layouts[6]
    dept=blueprint.get('department','Report'); team=blueprint.get('requesting_team',''); period=blueprint.get('period_label','Selected period'); audience=blueprint.get('audience','')
    evidence=blueprint.get('period_evidence',{}) or {}
    for s in blueprint.get('slides',[]):
        slide=prs.slides.add_slide(blank); typ=s['type']
        if typ=='cover':
            bg=slide.background.fill; bg.solid(); bg.fore_color.rgb=rgb(NAVY)
            text(slide,0.75,1.25,11.5,0.65,s['title'],30,True,WHITE)
            text(slide,0.78,2.05,10.8,0.55,s['subtitle'],18,False,'DCE8F2')
            text(slide,0.78,3.0,7.5,0.35,f"Requesting team: {team}",11,False,'DCE8F2')
            text(slide,0.78,3.45,7.5,0.35,f"Audience: {audience}",11,False,'DCE8F2')
            text(slide,0.78,5.95,10.5,0.3,"Automatically designed from the selected data, period and reporting brief",9,False,'B9C8D6')
            slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.78), Inches(5.62), Inches(1.4), Inches(0.05)).fill.solid(); slide.shapes[-1].fill.fore_color.rgb=rgb(GOLD); slide.shapes[-1].line.fill.background()
            continue
        title_bar(slide,s.get('title','Report'), s.get('subtitle',''))
        if typ=='executive_summary':
            rows=s.get('findings',[])
            add_kpi(slide,0.6,1.45,2.25,'Period cases',f"{evidence.get('case_count',0):,}")
            add_kpi(slide,3.0,1.45,2.25,'Distinct wards',str(evidence.get('distinct_wards','Not available')))
            add_kpi(slide,5.4,1.45,2.25,'Period',blueprint.get('period_type',''))
            comp=(s.get('comparison') or {})
            change=comp.get('change_pct')
            add_kpi(slide,7.8,1.45,2.25,'Vs comparison',f"{change:+.1f}%" if isinstance(change,(int,float)) else 'Not available', RED if isinstance(change,(int,float)) and change<0 else BLUE)
            box(slide,0.6,2.8,12.1,3.65,LIGHT,LIGHT)
            text(slide,0.82,3.02,11.5,0.3,'What matters',13,True,NAVY)
            y=3.48
            for r in rows[:5]:
                text(slide,0.85,y,0.45,0.32,str(r.get('id','•')),9,True,GOLD)
                text(slide,1.28,y,10.95,0.55,_finding_text(r),10,False,DARK); y+=0.58
        elif typ=='daily_snapshot':
            metrics=s.get('metrics',[])
            cols=3; gap=0.22; card_w=(11.7-gap*2)/cols
            for i,(label,value) in enumerate(metrics):
                row=i//cols; col=i%cols
                add_kpi(slide,0.65+col*(card_w+gap),1.55+row*1.22,card_w,label,f"{value:,}" if isinstance(value,(int,float)) else str(value),BLUE if i in (0,2) else NAVY)
            pace=s.get('pace'); days=s.get('remaining_days')
            box(slide,0.65,4.25,11.7,1.55,LIGHT,LIGHT)
            text(slide,0.9,4.52,2.7,0.25,'Operational pacing',10,True,NAVY)
            pace_txt=(f"Suggested new wards per remaining working day: {pace:,} across {days} remaining working day(s)." if isinstance(pace,(int,float)) and isinstance(days,(int,float)) and days>0 else 'No pacing recommendation is calculated from the available evidence.')
            text(slide,0.9,4.9,10.9,0.55,pace_txt,10,False,DARK)
            text(slide,0.9,5.48,10.9,0.25,'The pace is a recommendation based on the configured ward benchmark and remaining Monday–Friday days, not an observed performance value.',8,False,'5C6B78')
        elif typ=='channel_time':
            channel=s.get('channel',[]) or []; hourly=s.get('hourly',[]) or []
            if channel:
                add_chart(slide,channel[:8],0.65,1.48,5.35,4.0,'Cases by channel')
            else:
                box(slide,0.65,1.48,5.35,4.0,LIGHT,LIGHT); text(slide,0.95,3.1,4.7,0.6,'Channel data not available.',11,False,'687783')
            if hourly:
                add_chart(slide,[{'value':f"{int(r['hour']):02d}:00",'cases':r['cases']} for r in hourly],6.25,1.48,6.05,4.0,'Cases by hour')
            else:
                box(slide,6.25,1.48,6.05,4.0,LIGHT,LIGHT); text(slide,6.6,3.1,5.2,0.6,'Hourly activity data not available.',11,False,'687783')
            add_insight_box(slide,0.65,5.62,11.65,0.85,s.get('insight',''))
        elif typ=='kpi_snapshot':
            metrics=s.get('metrics',[])
            widths=11.4/max(len(metrics),1)
            for i,(label,value) in enumerate(metrics):
                add_kpi(slide,0.75+i*widths,1.7,widths-0.18,label,value,BLUE if i==0 else NAVY)
            box(slide,0.75,3.15,11.55,2.65,LIGHT,LIGHT)
            text(slide,1.0,3.48,10.9,0.3,'Design decision',13,True,NAVY)
            text(slide,1.0,3.95,10.8,1.25,'The automatic designer selected a KPI snapshot because the selected period does not contain enough daily observations for a meaningful trend chart.',10,False,DARK)
            text(slide,1.0,5.35,10.8,0.3,'No trend is inferred from a single observation.',9,False,'5C6B78')
        elif typ=='trend':
            add_line(slide,s.get('data',[]),0.7,1.55,8.15,4.75)
            comp=s.get('comparison') or {}
            box(slide,9.15,1.55,3.45,4.75,LIGHT,LIGHT)
            text(slide,9.4,1.85,2.9,0.3,'Period position',12,True,NAVY)
            text(slide,9.4,2.4,2.7,0.25,'Cases',8,False,'687783'); text(slide,9.4,2.68,2.7,0.42,f"{evidence.get('case_count',0):,}",22,True,BLUE)
            if comp.get('comparison_case_count') is not None:
                text(slide,9.4,3.35,2.7,0.25,'Comparison cases',8,False,'687783'); text(slide,9.4,3.63,2.7,0.42,f"{comp['comparison_case_count']:,}",18,True,NAVY)
            text(slide,9.4,4.35,2.7,0.25,'Interpretation',8,False,'687783')
            note='Use the trend to identify concentration or change; do not infer causality from volume alone.'
            text(slide,9.4,4.62,2.75,1.0,note,9,False,DARK)
        elif typ=='breakdown':
            if s.get('chart_type')=='donut':
                add_donut(slide,s.get('data',[]),0.8,1.5,7.0,4.0)
            else:
                add_chart(slide,s.get('data',[]),0.7,1.5,7.55,4.15,s.get('subtitle','Cases by segment'))
            add_insight_box(slide,8.45,1.5,4.0,4.15,s.get('insight',''))
        elif typ=='coverage':
            val=s.get('value'); total=s.get('total')
            display=f"{val:,}" if isinstance(val,int) else 'Not available'
            add_kpi(slide,0.75,1.65,3.0,'Wards represented',display,BLUE)
            if total:
                pct=(float(val)/float(total)*100) if isinstance(val,(int,float)) else None
                add_kpi(slide,3.95,1.65,3.0,'Configured total',f"{total:,}",NAVY)
                add_kpi(slide,7.15,1.65,3.0,'Coverage',f"{pct:.1f}%" if pct is not None else 'Not available',GREEN if pct==100 else BLUE)
            rows=s.get('corridor',[])
            cca=s.get('cca',[]) or []
            if rows:
                cats=[str(r.get('corridor','')) for r in rows]; covered=[float(r.get('covered',0)) for r in rows]; missing=[float(r.get('missing',0)) for r in rows]
                cd=ChartData(); cd.categories=cats; cd.add_series('Covered',covered); cd.add_series('Missing',missing)
                ch=slide.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED, Inches(0.75), Inches(3.05), Inches(7.0), Inches(2.55), cd).chart; ch.has_legend=True; ch.legend.position=XL_LEGEND_POSITION.BOTTOM
                try:
                    ch.legend.font.name=FONT; ch.legend.font.size=Pt(9)
                except Exception: pass
                for i,c in enumerate([BLUE,GOLD]): ch.series[i].format.fill.solid(); ch.series[i].format.fill.fore_color.rgb=rgb(c)
            if cca:
                box(slide,8.0,3.05,4.15,2.55,WHITE,MID)
                text(slide,8.25,3.25,3.65,0.25,'CCA position',10,True,NAVY)
                text(slide,8.25,3.56,1.55,0.2,'CCA',7,True,'687783'); text(slide,10.25,3.56,0.55,0.2,'Cov.',7,True,'687783'); text(slide,11.05,3.56,0.7,0.2,'Rate',7,True,'687783')
                y=3.84
                for r in sorted(cca,key=lambda z: (float(z.get('covered',0))/float(z.get('target',1)) if z.get('target') else 0))[:6]:
                    target=float(r.get('target',0) or 0); cov=float(r.get('covered',0) or 0); rate=(cov/target*100) if target else 0
                    label=str(r.get('cca',''))[:20]
                    text(slide,8.25,y,1.85,0.25,label,7.2,False,DARK); text(slide,10.25,y,0.55,0.25,f'{int(cov)}/{int(target)}',7.2,False,DARK); text(slide,11.05,y,0.7,0.25,f'{rate:.0f}%',7.2,False,DARK); y+=0.31
                if len(cca)>6: text(slide,8.25,5.48,3.6,0.2,f"+ {len(cca)-6} more CCA rows in addendum",7,False,'687783')
            add_insight_box(slide,0.75,5.78,11.4,0.72,s.get('insight',''))
        elif typ=='actions':
            rows=s.get('data',[])
            if rows:
                # A compact decision register: what is observed, what should happen, and how success is checked.
                text(slide,0.85,1.38,2.0,0.22,'PRIORITY',7,True,'687783'); text(slide,1.95,1.38,5.15,0.22,'DECISION / ACTION',7,True,'687783'); text(slide,7.1,1.38,3.45,0.22,'WHY NOW',7,True,'687783'); text(slide,10.6,1.38,1.55,0.22,'EVIDENCE',7,True,'687783')
                y=1.68
                for r in rows[:5]:
                    box(slide,0.75,y,11.75,0.86,WHITE,MID)
                    priority=str(r.get('priority','Review')); accent=RED if priority.lower() in {'critical','high'} else GOLD
                    text(slide,0.95,y+0.15,0.85,0.25,priority,8,True,accent)
                    action=str(r.get('recommended_action',r.get('recommendation','Review the evidence and assign the appropriate operational response.')))
                    reason=str(r.get('trigger',r.get('finding',r.get('decision_gate','Evidence requires management review.'))))
                    evidence_ref=str(r.get('evidence_ref','Evidence register'))
                    text(slide,1.95,y+0.10,4.95,0.58,action,8.5,True,NAVY)
                    text(slide,7.1,y+0.10,3.25,0.58,reason,8,False,DARK)
                    text(slide,10.6,y+0.10,1.55,0.58,evidence_ref,7.5,False,'687783')
                    y+=0.98
            else:
                box(slide,0.8,1.65,11.5,2.0,LIGHT,LIGHT); text(slide,1.05,2.1,10.9,0.55,'No evidence-backed management actions were produced.',12,True,GREEN); text(slide,1.05,2.78,10.9,0.45,'The report does not invent actions where the available evidence does not support them.',9,False,DARK)
        elif typ=='quality':
            rows=s.get('data',[])
            y=1.55
            if not rows:
                box(slide,0.75,1.55,11.75,2.0,LIGHT,LIGHT); text(slide,1.0,2.05,10.9,0.55,'No material data-quality exception was detected in the mapped checks.',12,True,GREEN); text(slide,1.0,2.72,10.9,0.45,'This means the report can use the available fields without a known blocking quality issue.',9,False,DARK)
            for r in rows[:6]:
                sev=str(r.get('severity','Review')); sev_l=sev.lower(); accent=RED if sev_l in {'high','critical','red'} else GOLD
                box(slide,0.75,y,11.75,0.72,WHITE,MID)
                text(slide,0.95,y+0.10,1.0,0.25,sev,8,True,accent)
                text(slide,1.9,y+0.08,10.25,0.48,str(r.get('finding',r.get('rule',''))),9,False,DARK); y+=0.81
            add_insight_box(slide,0.75,6.48,11.75,0.45,'These are limitations or control exceptions that affect how the report should be interpreted. They are not automatically failures of the underlying operation.')
        elif typ=='method':
            box(slide,0.75,1.55,11.75,4.8,LIGHT,LIGHT)
            text(slide,1.0,1.85,10.9,0.35,'How to verify this report',13,True,NAVY)
            y=2.38
            for item in s.get('items',[]):
                text(slide,1.0,y,0.3,0.25,'•',10,True,GOLD); text(slide,1.3,y,10.55,0.48,str(item).capitalize(),9,False,DARK); y+=0.48
            text(slide,1.0,5.75,10.8,0.35,'Detailed calculations, source registers, exceptions and traceability belong in the analytical addendum.',9,False,'5C6B78')
        elif typ=='extreme_diagnostic_pareto':
            pareto=s.get('pareto',[]) or []
            box(slide,0.75,1.45,11.75,4.95,WHITE,MID)
            text(slide,1.0,1.72,10.9,0.35,'Pareto priority screen',14,True,NAVY)
            if pareto:
                add_chart(slide,[{'value':str(r.get('value','')),'cases':r.get('cases',0)} for r in pareto[:9]],1.0,2.18,10.7,3.55,'Largest concentration segments')
                top_n=min(3,len(pareto)); cum=float(pareto[top_n-1].get('cumulative_pct',0))
                text(slide,1.0,5.92,10.6,0.30,f'Cumulative share across the first {top_n} segment(s): {cum:.1f}%. Use this as a prioritisation signal, not a causal conclusion.',9,False,'5C6B78')
            else:
                text(slide,1.0,2.25,10.6,0.5,'No Pareto ranking was produced because the selected-period evidence did not contain a usable breakdown.',11,False,DARK)
        elif typ=='extreme_diagnostic_framework':
            fish=s.get('fishbone',[]) or []; five=s.get('five_whys',[]) or []
            box(slide,0.65,1.45,7.05,4.95,WHITE,MID); text(slide,0.92,1.72,6.4,0.35,'Fishbone investigation frame',13,True,NAVY)
            y=2.12
            for r in fish[:8]:
                text(slide,0.95,y,2.35,0.28,str(r.get('fishbone_category',''))[:28],8.5,True,DARK)
                text(slide,3.30,y,3.95,0.42,str(r.get('evidence_signal',''))[:105],8.5,False,DARK); y+=0.49
            box(slide,7.95,1.45,4.7,4.95,LIGHT,LIGHT); text(slide,8.22,1.72,4.15,0.35,'Five Whys prompts',13,True,NAVY)
            if five:
                y=2.15
                for i,r in enumerate(five[:3],1):
                    text(slide,8.22,y,4.0,0.28,f"{i}. {str(r.get('dimension','')).title()}",9,True,DARK)
                    text(slide,8.22,y+0.34,4.0,0.80,str(r.get('why_1','')),8.5,False,DARK)
                    y+=1.25
                text(slide,8.22,5.92,4.0,0.30,'Answers require verified operational evidence.',8.5,False,'5C6B78')
            else:
                text(slide,8.22,2.20,4.0,0.5,'No materially concentrated segment generated a Five Whys prompt.',9,False,DARK)
        elif typ=='extreme_predictive':
            pred=s.get('predictive',{}) or {}; series=s.get('series',[]) or []
            if series: add_line(slide,[{'date':r['date'],'cases':r['cases']} for r in series],0.75,1.55,8.0,4.7)
            box(slide,9.0,1.55,3.55,4.7,LIGHT,LIGHT); text(slide,9.25,1.85,2.9,0.3,'Predictive screen',12,True,NAVY)
            text(slide,9.25,2.35,2.9,0.25,'Historical observations',8,False,'687783'); text(slide,9.25,2.65,2.9,0.42,str(pred.get('historical_days','Not available')),20,True,BLUE)
            text(slide,9.25,3.35,2.9,0.25,'Trend',8,False,'687783'); text(slide,9.25,3.65,2.9,0.42,str(pred.get('direction','Not available')).title(),16,True,NAVY)
            text(slide,9.25,4.30,2.9,0.25,'Next-day screen',8,False,'687783'); text(slide,9.25,4.58,2.9,0.42,str(pred.get('next_day_screen','Not available')),18,True,BLUE)
            text(slide,9.25,5.25,2.9,0.65,'Simple trend only. It is not a guaranteed forecast and does not model causality or seasonality.',8,False,DARK)
        elif typ=='extreme_optimisation':
            rows=s.get('findings',[]) or []
            y=1.55
            for r in rows[:6]:
                box(slide,0.75,y,11.75,0.76,WHITE,MID)
                text(slide,0.95,y+0.10,1.15,0.25,str(r.get('maturity_level','L4')),8,True,GOLD)
                text(slide,2.0,y+0.07,9.9,0.28,str(r.get('finding',''))[:150],9,True,NAVY)
                text(slide,2.0,y+0.37,9.9,0.25,str(r.get('recommendation',''))[:170],8,False,DARK)
                y+=0.82
            if not rows: text(slide,0.8,1.65,11.5,0.6,'No optimisation candidates were produced from the available evidence.',11,False,'687783')
            gaps=s.get('gaps',[]) or []
            if gaps: text(slide,0.8,6.25,11.5,0.35,'Evidence gates: '+ ' | '.join(gaps[:2]),7.5,False,'5C6B78')
        elif typ=='voc':
            data=s.get('data') or {}
            box(slide,0.8,1.6,3.1,2.0,WHITE,MID); text(slide,1.05,1.95,2.5,0.25,'VoC responses',8,False,'687783'); text(slide,1.05,2.32,2.5,0.55,str(data.get('responses',0)),24,True,BLUE)
            box(slide,4.15,1.6,3.1,2.0,WHITE,MID); text(slide,4.4,1.95,2.5,0.25,'Positive / resolved',8,False,'687783'); text(slide,4.4,2.32,2.5,0.55,f"{data.get('positive_pct','Not available')}%",24,True,GREEN)
            text(slide,0.85,4.15,11.2,0.7,'VoC is shown only when supplied evidence is available and labelled for the selected reporting context.',10,False,DARK)
        footer(slide,dept,team,period)
    prs.save(out_path)
