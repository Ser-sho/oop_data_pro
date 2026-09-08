# OOP Corridor Reporting System — V3.13

## Report Quality & Daily Operations Framework

V3.11 builds on V3.8 and adds a deliberate dual-mode analytical layer while preserving the V3.8 daily framework.

V3.8 addressed two practical issues found during automatic-report testing:

1. Daily Operations reports must retain a mandatory operational core rather than allowing materiality scoring to remove important operational sections.
2. Automatically generated PowerPoint text must be constrained to its allocated shapes so long findings wrap/shrink instead of overlapping adjacent content.

### V3.8 daily framework

For a Daily report, the automatic designer now preserves an evidence-driven core including, when supported by the source data:

- Executive Summary
- Daily Operational Snapshot
- Ward & Geographic Coverage
- Channel & Hourly Activity
- Workflow / Resolution Position
- Service & Demand Mix
- Location / Entity Performance
- Priority / Risk Position
- Data Quality & Limitations
- Voice of Citizen when supplied
- Actions and Management Decisions
- Evidence and Method Note

Unavailable metrics are omitted or explicitly marked unavailable. The framework does not invent values.

### Layout controls

The automatic PowerPoint generator now uses word wrapping and PowerPoint text-to-fit behavior for generated text boxes. The daily snapshot, coverage, channel/time, quality, actions and method layouts were adjusted to reserve predictable space and reduce collision risk.

### QA

Blueprint QA now explicitly checks the daily mandatory framework and confirms that coverage and channel/time views are present when their evidence is available.

### Clean packaging rule

The distributable package contains source/configuration only. Do not package real operational datasets, generated reports, or the supplied PowerPoint template as required runtime assets.

### Architecture

Dataset → Period → Entity → Requesting Team → Data/Capabilities → Analysis → Analytical Intelligence → Evidence/Decision Governance → Mandatory/Optional Report Design → PowerPoint → Detailed Addendum → QA


## V3.11 — Extreme Analysis Presentation Hardening
V3.11 keeps the V3.11 dual-mode engine and separates the Extreme Analysis diagnostic content into dedicated Pareto and Diagnostic Investigation slides. Blueprint QA now checks Extreme analytical QA and the split diagnostic layers.

## V3.11 — Dual Analysis Mode + CIC Analytical Maturity Engine
V3.11 preserves Normal Analysis as the standard workflow and adds an explicit Extreme Analysis mode. Extreme Analysis activates evidence-gated maturity levels and methods: Pareto, Fishbone, Five Whys, control-gap review, recurrence/trend screening, simple predictive analysis where history supports it, and optimisation/BPM handover candidates. No root cause, forecast or optimisation claim is treated as confirmed without supporting evidence.


### V3.11 evidence-driven report insights, visual interpretation and concise evidence-engine addendum
Extreme Analysis now profiles the dominant Pareto segment across available workflow, ownership, demand, outcome and location fields, calculates within-segment share shifts against the selected-period baseline, links observable associations into the CIC Fishbone framework, and uses them to populate evidence-aware Five Whys prompts. These remain associations/hypotheses until independently verified. Final Report QA now runs after analytical intelligence, decision governance, Extreme Analysis and blueprint QA so the circulation gate reflects the complete report package.


## V3.12 — Adaptive evidence addendum
The Excel addendum now adapts to Normal vs Extreme Analysis, reporting period, audience, requesting team and stated reporting requirements. Normal mode remains a concise nine-sheet management/evidence pack. Extreme mode adds separate Extreme Overview, Pareto & Concentration, Diagnostic Investigation, Root Cause Investigation, Predictive & Control Outlook, and Extreme QA & Method sheets when supported by the evidence. Charts are added to the evidence sections where they improve interpretation.


## V3.13.1 — Context-aware evidence insights and adaptive visuals
Section insights are now derived from the selected period evidence rather than static explanatory text. Longer periods prioritise daily trend movement; Daily reports prioritise hourly arrival peaks. Demand, workflow, coverage, quality, priority and location insights adapt to the audience and available evidence while preserving the nine-sheet Normal addendum structure.
