# OOP Corridor Daily Operations Report — V2.3 Daily Ward Logic

This build keeps the supplied PowerPoint template's structure, fonts, colours and layout, while using real PowerPoint charts and the agreed daily/cumulative ward rules.

## Agreed daily ward rules
- **Reporting date is manual** and is never inferred from the latest timestamp.
- **Daily wards** means the distinct wards that had valid cases on that reporting date. It is an analytical measure, not a published movement-table column.
- **New wards** means the distinct wards covered on the reporting date that were **not already covered earlier in the same Monday-Friday reporting week**.
- **Running wards** means the cumulative unique wards covered from the Monday of the reporting week through the selected reporting date, displayed as `running/112` (or the supplied total for another municipality).
- **Still needed** means `total wards - running wards`, shown as the positive answer only.
- When later days are not yet available, the system calculates a **suggested new-wards-per-remaining-working-day pace** so the weekly ward target can still be reached by Friday.

## Slide rules
- **Slide 2 — Executive Coverage Snapshot:** shows daily cases, new wards, running wards and still needed. The movement table contains **Cases, New wards, Running total and Still needed**; there is no Daily wards column. If the week is incomplete, the attention message gives the required daily new-ward pace for the remaining Monday-Friday working days.
- **Slide 3 — Ward Coverage by Municipality / Region:** for Ekurhuleni, the municipality is divided into **North East Corridor (target 62)** and **South East Corridor (target 50)**. Covered is the **unique number of wards covered on the selected reporting date** in that corridor. Missing is `target - covered`, and `%` is covered/target × 100. The validation row separately preserves the 112 listed allocations / 111 unique master ward numbers issue.
- **Slide 4 — Channel and Time Coverage:** channel cases are for the selected reporting date. **New wards** is the unique new-ward count associated with each channel on that date, after checking prior days in the same reporting week. Hourly activity is also for the selected reporting date.
- **Slide 5:** real horizontal Top Services chart with X/Y axes and data labels.
- **Slide 7:** real horizontal Priority Control Load chart with X/Y axes and data labels.

## Ekurhuleni ward master validation
The supplied `EMM CCC & Wards.xlsx` is used as the allocation benchmark. It contains 112 listed allocations but 111 unique ward numbers because Ward 52 is allocated twice. SERSHO contains all 111 unique master wards plus one observed normalized ward number outside the master (Ward 71). These exceptions are flagged, not silently corrected.

## Excel addendum
The addendum is the evidence layer and includes:
- Daily Tracker
- Ward Mapping QA
- Ward Coverage Detail
- Missing Wards
- Corridor Coverage
- CCA Coverage
- Channel New Wards
- Ward Master Exceptions
- analytical charts and supporting calculations/evidence

## Run
```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app.py
```

For Ekurhuleni, the supplied ward master sets the configured allocation benchmark to 112 listed allocations. Reporting date and data close time remain manual.

The app auto-versions output files if a same-date report already exists.
## V2.4 — CCA tracker
- Adds a `CCA Daily Tracker` evidence sheet for the selected Monday-Friday reporting week.
- New wards are unique wards first seen that day within each CCA; running wards are cumulative unique wards for the CCA; still needed is target minus running.
- Management-facing CCA tracker omits the redundant Daily wards column.


## V2.5 — Single-day and retained ward history
- A one-day operations dataset is treated as a baseline when no prior ward history is available.
- The system calculates remaining working days and the required new wards per remaining working day to reach the configured weekly ward target.
- Separate daily uploads can build cumulative weekly ward coverage using compact retained ward/date evidence in the current Streamlit session.
- Historical raw case records are not copied into the retained history store.
- When prior retained history exists, New Wards means wards not previously covered in the reporting week; Running Wards is the cumulative unique ward count.
- The addendum records whether the selected day is a baseline or uses prior retained ward history.

## V2.6 — Multi-Municipality & Reporting-Week History
- Ward history is isolated by municipality/corridor **and** reporting week.
- The manually selected reporting date determines the Monday-Friday reporting week; upload date is never used to determine the week.
- Late reporting is supported: a Friday report prepared on Monday remains in that Friday's week; a Tuesday report for Monday starts the new Monday-Friday week.
- Separate municipalities/corridors never share ward history.
- A later upload for an already represented date replaces the compact ward/date evidence for that date instead of unioning stale wards, supporting corrected datasets.
- Retained history only contains compact date/ward/corridor/CCA evidence, not raw case data.
