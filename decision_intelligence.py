from __future__ import annotations
from typing import Any
import pandas as pd


def _owner_for(area: str, team: str) -> str:
    t = (team or '').strip()
    if t:
        return t
    return {
        'Coverage': 'Operations Team',
        'Performance': 'Operations Team',
        'Resolution': 'Operations Team',
        'Channel': 'Operations Team',
        'Service demand': 'Entity Team',
        'Location': 'Operations Team',
        'Priority': 'Management',
        'Data quality': 'Data / Reporting Team',
    }.get(area, 'Management')


def _horizon(priority: str, gate: str) -> str:
    if gate == 'Review before decision':
        return 'Before circulation / decision'
    if priority == 'High':
        return 'Next operating cycle'
    return 'Routine review'


def build_decision_intelligence(
    analytical_intelligence: dict[str, Any],
    requesting_team: str = '',
    audience: str = '',
) -> dict[str, Any]:
    """V3.6 converts evidence-backed findings into governed management actions.

    It does not invent deadlines, named people, budgets or target values. It creates
    action-control metadata only: owner role, trigger, decision gate, horizon and
    verification step. This keeps actions usable while preserving evidence limits.
    """
    findings = analytical_intelligence.get('findings', pd.DataFrame())
    if not isinstance(findings, pd.DataFrame):
        findings = pd.DataFrame(findings or [])

    actions = []
    escalations = []
    for _, row in findings.iterrows():
        fid = str(row.get('id', '')).strip()
        if not fid:
            continue
        priority = str(row.get('priority', 'Normal'))
        gate = str(row.get('decision_gate', 'Review before decision'))
        confidence = str(row.get('confidence', 'Low'))
        area = str(row.get('area', 'General'))
        recommendation = str(row.get('action', row.get('recommendation', ''))).strip()
        evidence_ref = str(row.get('evidence_ref', '')).strip()
        owner = _owner_for(area, requesting_team)
        trigger = (
            'Evidence is insufficient for a decision; validate the cited evidence first.'
            if gate == 'Review before decision' else
            f"Finding {fid} is High priority and evidence is {confidence} confidence." if priority == 'High' else
            f"Finding {fid} remains relevant for routine operational review."
        )
        verify = (
            f"Re-run or inspect {evidence_ref} and record the outcome before closing the action."
            if evidence_ref else 'Record the evidence used to verify the action outcome.'
        )
        action_id = fid.replace('AI-F', 'DI-A')
        actions.append({
            'action_id': action_id,
            'finding_id': fid,
            'priority': priority,
            'area': area,
            'decision_gate': gate,
            'confidence': confidence,
            'owner_role': owner,
            'trigger': trigger,
            'recommended_action': recommendation,
            'evidence_ref': evidence_ref,
            'verification_step': verify,
            'review_horizon': _horizon(priority, gate),
            'status': 'Open',
        })
        if priority == 'High' or gate == 'Review before decision':
            escalations.append({
                'finding_id': fid,
                'priority': priority,
                'decision_gate': gate,
                'escalation': 'Escalate for management review' if gate == 'Decision-ready' and priority == 'High' else 'Hold for evidence review',
                'reason': trigger,
                'owner_role': owner,
                'evidence_ref': evidence_ref,
            })

    adf = pd.DataFrame(actions)
    edf = pd.DataFrame(escalations)
    qa_rows = []
    for _, r in adf.iterrows():
        for check, ok in [
            ('Action linked to finding', bool(str(r.get('finding_id','')).strip())),
            ('Action has evidence reference', bool(str(r.get('evidence_ref','')).strip())),
            ('Action has decision gate', bool(str(r.get('decision_gate','')).strip())),
            ('Action has verification step', bool(str(r.get('verification_step','')).strip())),
            ('Action does not invent named owner', not any(x in str(r.get('owner_role','')).lower() for x in ['mr ', 'mrs ', 'ms ', '@'])),
            ('Action has governed horizon', str(r.get('review_horizon','')) in {'Next operating cycle','Routine review','Before circulation / decision'}),
        ]:
            qa_rows.append({'check': check, 'item': r['action_id'], 'status': 'PASS' if ok else 'FAIL'})

    return {
        'version': '3.6',
        'audience': audience,
        'requesting_team': requesting_team,
        'actions': adf,
        'escalations': edf,
        'qa': pd.DataFrame(qa_rows),
        'summary': {
            'action_count': int(len(adf)),
            'high_priority_actions': int((adf.get('priority', pd.Series(dtype=str)) == 'High').sum()) if not adf.empty else 0,
            'decision_ready_actions': int((adf.get('decision_gate', pd.Series(dtype=str)) == 'Decision-ready').sum()) if not adf.empty else 0,
            'review_before_decision': int((adf.get('decision_gate', pd.Series(dtype=str)) == 'Review before decision').sum()) if not adf.empty else 0,
        },
        'rules': {
            'no_invented_named_owners': True,
            'no_invented_deadlines': True,
            'every_action_links_to_finding': True,
            'every_action_requires_evidence': True,
            'verification_required': True,
            'decision_gate_inherited_from_v35': True,
        },
    }
