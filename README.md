# OOP Corridor Reporting System — V3.8

## Report Quality & Daily Operations Framework

V3.8 builds on V3.7 and addresses two practical issues found during automatic-report testing:

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
