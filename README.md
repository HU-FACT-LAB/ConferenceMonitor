# Conference & Opportunity Tracker

A free-tier-friendly shared conference monitor for a research group or network of colleagues.

## What this version does

- Shared master catalog of conference series
- Separate annual/biennial conference editions
- Deadline records with official-source provenance and verification dates
- Filters by field and deadline horizon
- Personal watch lists for students, lab members, and colleagues
- Lightweight profile keys (no account required)
- Conference suggestion form
- `.ics` export for visible deadlines
- Local/demo mode if Airtable is not configured
- Airtable mode for persistent shared data

Starter series: AOAC, ACS Spring, ACS Fall, CSC, ASMS, CIFST, IFT FIRST, IMSC, Lake Louise MS/MS, RAFA, IUFoST, IAFP, and NACRW.

## Run locally

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Without Airtable secrets, the app runs from the bundled CSV files.

## Airtable

Follow `AIRTABLE_SCHEMA.md` to create the shared backend. Import the three CSV files in `data/` for the starter catalog.

## Deploy on Streamlit Community Cloud

1. Sign in to Streamlit Community Cloud with GitHub.
2. Create a new app from `HU-FACT-LAB/ConferenceMonitor`.
3. Set the main file to `app.py`.
4. In **App settings -> Secrets**, copy the structure from `.streamlit/secrets.example.toml` and replace the placeholders with the Airtable Base ID and personal access token.
5. Reboot the app.

The deployed app will have a shareable `streamlit.app` URL.

## Personal watch lists

Each user creates a lightweight profile. The app generates a private profile key and adds it to the URL. Their watch list is stored in one Airtable record and can be changed later. This avoids requiring students or colleagues to create Airtable accounts.

## Data quality rule

Never carry a prior-year deadline forward as confirmed. Each confirmed deadline should include its edition/year, official source URL, verification date, and Confirmed status. Unknown future values should remain blank/TBD.
