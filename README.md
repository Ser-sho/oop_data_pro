# OOP Corridor Daily Operations Report — V1 Step 3

Fast-build foundation for an operational data-analysis and reporting system.

## Current capabilities
- Excel/CSV upload and sheet selection
- Dataset profiling and mapped data dictionary
- Data-quality checks
- Configurable municipality/corridor and total ward count
- Manual reporting date, period covered and data close time
- Deterministic operational analysis
- Management findings with IDs
- Evidence register for findings/recommendations
- Recommendation triggers
- Lightweight evidence-reference QA

## Run on Windows
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Design rule
Calculations and evidence are deterministic. AI narrative, PowerPoint generation and the analytical addendum are separate layers to be added next.
