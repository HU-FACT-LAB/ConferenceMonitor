import os
import secrets
import string
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

APP_TITLE = "Conference & Opportunity Tracker"
ROOT = Path(__file__).parent
DATA = ROOT / "data"

st.set_page_config(page_title=APP_TITLE, page_icon="📅", layout="wide")

# ---------- Configuration ----------
def get_secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

AIRTABLE_BASE_ID = get_secret("AIRTABLE_BASE_ID")
AIRTABLE_TOKEN = get_secret("AIRTABLE_TOKEN")
AIRTABLE_ENABLED = bool(AIRTABLE_BASE_ID and AIRTABLE_TOKEN)

TABLES = {
    "series": get_secret("AIRTABLE_SERIES_TABLE", "Conference Series"),
    "editions": get_secret("AIRTABLE_EDITIONS_TABLE", "Conference Editions"),
    "deadlines": get_secret("AIRTABLE_DEADLINES_TABLE", "Deadlines"),
    "profiles": get_secret("AIRTABLE_PROFILES_TABLE", "Profiles"),
    "suggestions": get_secret("AIRTABLE_SUGGESTIONS_TABLE", "Suggestions"),
}

HEADERS = {"Authorization": f"Bearer {AIRTABLE_TOKEN}", "Content-Type": "application/json"} if AIRTABLE_ENABLED else {}

# ---------- Airtable helpers ----------
def airtable_url(table):
    return f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{quote(table, safe='')}"

def airtable_list(table, params=None):
    records = []
    p = dict(params or {})
    while True:
        r = requests.get(airtable_url(table), headers=HEADERS, params=p, timeout=20)
        r.raise_for_status()
        payload = r.json()
        records.extend(payload.get("records", []))
        if not payload.get("offset"):
            break
        p["offset"] = payload["offset"]
    return records

def airtable_create(table, fields):
    r = requests.post(airtable_url(table), headers=HEADERS, json={"fields": fields}, timeout=20)
    r.raise_for_status()
    return r.json()

def airtable_update(table, record_id, fields):
    url = f"{airtable_url(table)}/{record_id}"
    r = requests.patch(url, headers=HEADERS, json={"fields": fields}, timeout=20)
    r.raise_for_status()
    return r.json()

def records_to_df(records):
    rows = []
    for rec in records:
        row = dict(rec.get("fields", {}))
        row["_record_id"] = rec.get("id")
        rows.append(row)
    return pd.DataFrame(rows)

# ---------- Data loading ----------
@st.cache_data(ttl=21600, show_spinner=False)
def load_core_data():
    if AIRTABLE_ENABLED:
        series = records_to_df(airtable_list(TABLES["series"]))
        editions = records_to_df(airtable_list(TABLES["editions"]))
        deadlines = records_to_df(airtable_list(TABLES["deadlines"]))
    else:
        series = pd.read_csv(DATA / "conference_series.csv")
        editions = pd.read_csv(DATA / "conference_editions.csv")
        deadlines = pd.read_csv(DATA / "deadlines.csv")
    return series, editions, deadlines

def normalize_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"true", "1", "yes", "y"}

def parse_list(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in str(v).split(",") if x.strip()]

def generate_profile_key():
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(10))

def get_profile(profile_key):
    if not (AIRTABLE_ENABLED and profile_key):
        return None
    formula = f"{{Profile Key}}='{profile_key.replace(chr(39), '')}'"
    rows = airtable_list(TABLES["profiles"], {"filterByFormula": formula, "maxRecords": 1})
    return rows[0] if rows else None

def create_profile(display_name, role, watched):
    key = generate_profile_key()
    fields = {
        "Profile Key": key,
        "Display Name": display_name.strip() or "Anonymous",
        "Role": role,
        "Watched Series": ", ".join(sorted(watched)),
        "Created At": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "Updated At": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    rec = airtable_create(TABLES["profiles"], fields)
    return key, rec

def update_profile(rec, watched):
    fields = {
        "Watched Series": ", ".join(sorted(watched)),
        "Updated At": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    return airtable_update(TABLES["profiles"], rec["id"], fields)

def make_ics(deadlines_df):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Conference Tracker//EN"]
    for _, r in deadlines_df.iterrows():
        d = pd.to_datetime(r.get("Deadline Date"), errors="coerce")
        if pd.isna(d):
            continue
        day = d.strftime("%Y%m%d")
        uid = str(r.get("Deadline ID", f"deadline-{day}")).replace(" ", "-")
        summary = f"{r.get('Short Name', r.get('Series Code','Conference'))}: {r.get('Name','Deadline')}"
        source = str(r.get("Official Source URL", "") or "")
        description = f"Type: {r.get('Type','')}"
        if source:
            description += f"\\nOfficial source: {source}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}@conference-tracker",
            f"DTSTART;VALUE=DATE:{day}",
            f"DTEND;VALUE=DATE:{day}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)

# ---------- Load & normalize ----------
series, editions, deadlines = load_core_data()

for df in (series, editions, deadlines):
    df.columns = [str(c).strip() for c in df.columns]

if "Active" in series.columns:
    series = series[series["Active"].map(normalize_bool)]

for col in ["Start Date", "End Date"]:
    if col in editions.columns:
        editions[col] = pd.to_datetime(editions[col], errors="coerce")
if "Deadline Date" in deadlines.columns:
    deadlines["Deadline Date"] = pd.to_datetime(deadlines["Deadline Date"], errors="coerce")

series_small = series[[c for c in ["Series Code", "Conference Name", "Short Name", "Organizer", "Categories", "Official URL", "Cadence"] if c in series.columns]].copy()
editions = editions.merge(series_small, on="Series Code", how="left", suffixes=("", "_series"))
deadlines = deadlines.merge(series_small, on="Series Code", how="left", suffixes=("", "_series"))

# ---------- Profile handling ----------
qp = st.query_params
profile_key = str(qp.get("profile", "") or "").strip().upper()
profile = None
watched_codes = []

if profile_key and AIRTABLE_ENABLED:
    try:
        profile = get_profile(profile_key)
        if profile:
            watched_codes = parse_list(profile["fields"].get("Watched Series", ""))
    except Exception as e:
        st.warning(f"Could not load this profile right now: {e}")

# ---------- Header ----------
left, right = st.columns([4, 1])
with left:
    st.title(APP_TITLE)
    st.caption("One shared catalog; personalized watch lists for students, lab members, and colleagues.")
with right:
    if AIRTABLE_ENABLED:
        st.success("Live database")
    else:
        st.info("Demo data")

if not AIRTABLE_ENABLED:
    st.warning(
        "This deployment is using the bundled demo data. Configure Airtable secrets to enable "
        "persistent personal watch lists and conference suggestions."
    )

# ---------- Sidebar filters ----------
with st.sidebar:
    st.header("View")
    if profile:
        st.success(f"Profile: {profile['fields'].get('Display Name', profile_key)}")
        if st.button("View all instead"):
            st.query_params.clear()
            st.rerun()
    elif profile_key:
        st.warning("Profile key not found.")

    horizon = st.slider("Deadline horizon (days)", 30, 730, 365, step=30)
    all_categories = sorted({
        cat for v in series.get("Categories", pd.Series(dtype=str)).dropna()
        for cat in parse_list(v)
    })
    selected_categories = st.multiselect("Fields", all_categories)

    if watched_codes:
        personal_only = st.toggle("My watched conferences only", value=True)
    else:
        personal_only = False

# ---------- Filtering helpers ----------
def series_passes(code, categories):
    if personal_only and code not in watched_codes:
        return False
    if not categories:
        return True
    row = series[series["Series Code"] == code]
    if row.empty:
        return False
    cats = set(parse_list(row.iloc[0].get("Categories", "")))
    return bool(cats.intersection(categories))

today = pd.Timestamp(date.today())
deadline_cutoff = today + pd.Timedelta(days=horizon)

deadlines_view = deadlines.copy()
deadlines_view = deadlines_view[
    deadlines_view["Deadline Date"].notna()
    & (deadlines_view["Deadline Date"] >= today)
    & (deadlines_view["Deadline Date"] <= deadline_cutoff)
]
deadlines_view = deadlines_view[
    deadlines_view["Series Code"].map(lambda x: series_passes(x, selected_categories))
]
deadlines_view["Days Left"] = (deadlines_view["Deadline Date"] - today).dt.days
deadlines_view = deadlines_view.sort_values(["Deadline Date", "Short Name"], na_position="last")

editions_view = editions.copy()
if "End Date" in editions_view.columns:
    editions_view = editions_view[
        editions_view["End Date"].isna() | (editions_view["End Date"] >= today)
    ]
editions_view = editions_view[
    editions_view["Series Code"].map(lambda x: series_passes(x, selected_categories))
]
editions_view = editions_view.sort_values(["Start Date", "Short Name"], na_position="last")

# ---------- Tabs ----------
tab_deadlines, tab_meetings, tab_watch, tab_suggest = st.tabs(
    ["Upcoming deadlines", "Meetings", "My watch list", "Suggest a meeting"]
)

with tab_deadlines:
    st.subheader("Upcoming deadlines")
    if deadlines_view.empty:
        st.info("No confirmed deadlines match the current filters.")
    else:
        urgent = (deadlines_view["Days Left"] <= 30).sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Matching deadlines", len(deadlines_view))
        c2.metric("Within 30 days", int(urgent))
        c3.metric("Conferences represented", deadlines_view["Series Code"].nunique())

        display_cols = [c for c in [
            "Deadline Date", "Days Left", "Short Name", "Type", "Name",
            "Status", "Official Source URL", "Last Verified"
        ] if c in deadlines_view.columns]
        display = deadlines_view[display_cols].copy()
        if "Deadline Date" in display:
            display["Deadline Date"] = display["Deadline Date"].dt.date
        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Official Source URL": st.column_config.LinkColumn("Official source"),
            },
        )
        st.download_button(
            "Download these deadlines to calendar (.ics)",
            data=make_ics(deadlines_view),
            file_name="conference_deadlines.ics",
            mime="text/calendar",
        )

with tab_meetings:
    st.subheader("Upcoming meetings")
    if editions_view.empty:
        st.info("No upcoming meetings match the current filters.")
    else:
        display_cols = [c for c in [
            "Start Date", "End Date", "Short Name", "Edition Name",
            "City", "Region/Country", "Venue", "Status", "Event URL"
        ] if c in editions_view.columns]
        display = editions_view[display_cols].copy()
        for col in ["Start Date", "End Date"]:
            if col in display:
                display[col] = display[col].dt.date
        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            column_config={"Event URL": st.column_config.LinkColumn("Official page")},
        )

with tab_watch:
    st.subheader("Personal watch list")
    all_codes = series["Series Code"].tolist()
    label_map = dict(zip(series["Series Code"], series["Conference Name"]))
    defaults = watched_codes if profile else []

    if not AIRTABLE_ENABLED:
        st.info("Persistent personal watch lists become available after Airtable is configured.")
        st.multiselect(
            "Preview a watch list",
            all_codes,
            default=defaults,
            format_func=lambda x: label_map.get(x, x),
            disabled=True,
        )
    elif profile:
        selected = st.multiselect(
            "Conferences to monitor",
            all_codes,
            default=[x for x in defaults if x in all_codes],
            format_func=lambda x: label_map.get(x, x),
        )
        if st.button("Save my watch list", type="primary"):
            try:
                update_profile(profile, selected)
                st.success("Watch list saved.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Could not save: {e}")
        st.caption(f"Profile key: {profile_key}. Bookmark this page to return to your watch list.")
    else:
        st.write(
            "Create a lightweight profile. No password is required; the generated profile key is "
            "your private bookmark for editing this watch list."
        )
        with st.form("create_profile"):
            display_name = st.text_input("Display name", placeholder="e.g., Yaxi / MSc student / Colleague")
            role = st.selectbox("Role", ["Faculty", "Postdoc", "Graduate student", "Undergraduate", "Staff", "Other"])
            selected = st.multiselect(
                "Conferences to monitor",
                all_codes,
                format_func=lambda x: label_map.get(x, x),
            )
            submitted = st.form_submit_button("Create my watch list")
        if submitted:
            try:
                key, _ = create_profile(display_name, role, selected)
                st.query_params["profile"] = key
                st.success("Profile created.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not create profile: {e}")

with tab_suggest:
    st.subheader("Suggest another conference")
    st.write("Suggestions go to the shared catalog administrator for review before becoming visible to everyone.")
    if not AIRTABLE_ENABLED:
        st.info("Suggestions become available after Airtable is configured.")
    else:
        with st.form("suggestion"):
            new_name = st.text_input("Conference or meeting name")
            new_url = st.text_input("Official website (if known)")
            note = st.text_area("Why should we monitor it? / relevant field")
            submitted = st.form_submit_button("Submit suggestion")
        if submitted:
            if not new_name.strip():
                st.error("Please enter a conference name.")
            else:
                sid = "SUG-" + datetime.utcnow().strftime("%Y%m%d%H%M%S")
                fields = {
                    "Suggestion ID": sid,
                    "Profile Key": profile_key or "",
                    "Conference Name": new_name.strip(),
                    "Official URL": new_url.strip(),
                    "Note": note.strip(),
                    "Status": "New",
                    "Created At": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                }
                try:
                    airtable_create(TABLES["suggestions"], fields)
                    st.success("Suggestion submitted.")
                except Exception as e:
                    st.error(f"Could not submit suggestion: {e}")

st.divider()
st.caption(
    "Dates marked Confirmed should be traceable to the linked official source. "
    "TBD means the organizer has not yet announced that item."
)
