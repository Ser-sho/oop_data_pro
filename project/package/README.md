# OOP Corridor Reporting System — V3.7

## V3.7 — Multi-Entity / Multi-Team Intelligence

V3.7 extends the V3.6 evidence and decision-governance foundation with a reusable configuration layer for different departments/entities and requesting internal teams.

### Core flow

**Source data → profiling → period selection → entity/team configuration → capability detection → report planning → analytical intelligence → evidence/confidence → decision/action governance → intelligent report design → PowerPoint + analytical addendum**

### V3.7 entity/team configuration

- Department/entity is a report identity, not a hardcoded analysis path.
- Entity profiles provide terminology and planning defaults only.
- Requesting teams have configurable focus/detail/decision style.
- Generic profile works for departments not represented by a preset.
- Example neutral presets are available for SASSA, Home Affairs, Health and Education.
- The supplied dataset remains authoritative for actual metrics and capabilities.
- Profiles cannot create unsupported KPIs or override source fields.
- Unsupported requested metrics remain explicit planner gaps.
- The same source dataset can be planned differently for different internal teams/audiences.

### Existing intelligence layers

- V3.0 explicit Daily/Weekly/Monthly/Quarterly/YTD/Annual/Custom reporting periods.
- V3.1 dynamic report planning.
- V3.2 automatic report designer/generator.
- V3.3 materiality- and audience-driven slide selection.
- V3.4 analytical intelligence: finding → implication → recommendation → evidence.
- V3.5 evidence/confidence/decision gates.
- V3.6 action governance and escalation controls.
- V3.7 multi-entity/multi-team configuration.

### Privacy and packaging

- Operational datasets are not packaged with the source project.
- Generated reports are not packaged with the source project.
- A supplied PowerPoint template is optional compatibility input, not a required dependency for automatic reporting.
- Raw data remains local to the application unless the user deliberately adds an external integration in a future version.
- Entity profiles are configuration, not evidence.

### Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Clean package policy

Source/configuration/reference code only. Do not add real operational data, generated outputs, secrets, or environment-specific caches to the distributable package.
