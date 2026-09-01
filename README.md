# OOP Corridor Daily Operations Report — V1 Step 8

Step 8 adds evidence traceability to the report/addendum workflow.

## New
- Evidence IDs linked to findings and recommendations.
- Concrete evidence detail with values and calculation logic.
- Traceability QA checks.
- Excel addendum includes an Evidence Detail sheet.
- Existing PowerPoint, template intelligence, audience and analysis features are retained.

Run with:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app.py
```

For Ekurhuleni, enter **112** as total wards. Reporting date and data close time remain manual.


## Step 9 — Final Report QA
The app now runs final QA before report generation. Critical failures block PowerPoint generation; warnings produce REVIEW REQUIRED. The Excel addendum includes a Final Report QA sheet. Reporting date and data close time remain manual.

## Template Mapper + VOC + date-aligned time analysis
This build edits the existing template shapes in place. It does not add chart images over the sample chart areas. Sample bars are resized using their existing fills, fonts and positions. RAG status is applied as a real fill to the existing status shape. The selected reporting date controls daily Created On/hour analysis. An optional VOC workbook can be uploaded and its supported metrics are surfaced without inventing unsupported measures.
