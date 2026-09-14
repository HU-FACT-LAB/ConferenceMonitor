import secrets
import string
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

APP_TITLE = "Conference & Opportunity Tracker"
ROOT = Path(__file__).parent
DATA = ROOT / "data"

st.set_page_config(page_title=APP_TITLE, page_icon="📅", layout="wide")


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

HEADERS = (
    {"Authorization": f"Bearer {AIRTABLE_TOKEN}", "Content-Type": "application/json"}
    if AIRTABLE_ENABLED
    else {}
)


def airtable_url(table):
    return f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{quote(table, safe='')}"


def airtable_list(table, params=None):
    records = []
    current_params = dict(params or {})
    while True:
        response = requests.get(
            airtable_url(table), headers=HEADERS, params=current_params, timeout=20
        )
        response.raise_for_status()
        payload = response.json()
        records.extend(payload.get("records", []))
        offset = payload.get("offset")
        if not offset:
            return records
        current_params["offset"] = offset


def airtable_create(table, fields):
    response = requests.post(
        airtable_url(table), headers=HEADERS, json={"fields": fields}, timeout=20
    )
    response.raise_for_status()
    return response.json()


def airtable_update(table, record_id, fields):
    response = requests.patch(
        f"{airtable_url(table)}/{record_id}",
        headers=HEADERS,
        json={"fields": fields},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def records_to_df(records):
    rows = []
    for record in records:
        row = dict(record.get("fields", {}))
        row["_record_id"] = record.get("id")
        rows.append(row)
    return pd.DataFrame(rows)


@st.cache_data(ttl=21600, show_spinner=False)
def load_core_data():
    if AIRTABLE_ENABLED:
        return (
            records_to_df(airtable_list(TABLES["series"])),
            records_to_df(airtable_list(TABLES["editions"])),
            records_to_df(airtable_list(TABLES["deadlines"])),
        )
    return (
        pd.read_csv(DATA / "conference_series.csv"),
        pd.read_csv(DATA / "conference_editions.csv"),
        pd.read_csv(DATA / "deadlines.csv"),
    )


def normalize_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def parse_list(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def generate_profile_key():
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(10))


def get_profile(profile_key):
    if not (AIRTABLE_ENABLED and profile_key):
        return None
    safe_key = profile_key.replace("'", "")
    formula = f"{{Profile Key}}='{safe_key}'"
    rows = airtable_list(TABLES["profiles"], {"filterByFormula": formula, "maxRecords": 1})
    return rows[0] if rows else None


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_profile(display_name, role, watched):
    key = generate_profile_key()
    record = airtable_create(
        TABLES["profiles"],
        {
            "Profile Key": key,
            "Display Name": display_name.strip() or "Anonymous",
            "Role": role,
            "Watched Series": ", ".join(sorted(watched)),
            "Created At": utc_now(),
            "Updated At": utc_now(),
        },
    )
    return key, record


def update_profile(record, watched):
    return airtable_update(
        TABLES["profiles"],
        record["id"],
        {"Watched Series": ", ".join(sorted(watched)), "Updated At": utc_now()},
    )


def make_ics(deadlines_df):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Conference Tracker//EN"]
    for _, row in deadlines_df.iterrows():
        deadline = pd.to_datetime(row.get("Deadline Date"), errors="coerce")
        if pd.isna(deadline):
            continue
        day = deadline.strftime("%Y%m%d")
        uid = str(row.get("Deadline ID", f"deadline-{day}")).replace(" ", "-")
        summary = f"{row.get('Short Name', row.get('Series Code', 'Conference'))}: {row.get('Name', 'Deadline')}"
        source = str(row.get("Official Source URL", "") or "")
        description = f"Type: {row.get('Type', '')}"
        if source:
            description += f"\\nOfficial source: {source}"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}@conference-tracker",
                f"DTSTART;VALUE=DATE:{day}",
                f"DTEND;VALUE=DATE:{day}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


series, editions, deadlines = load_core_data()
for frame in (series, editions, deadlines):
    frame.columns = [str(column).strip() for column in frame.columns]

if "Active" in series.columns:
    series = series[series["Active"].map(normalize_bool)]

for column in ("Start Date", "End Date"):
    if column in editions.columns:
        editions[column] = pd.to_datetime(editions[column], errors="coerce")
if "Deadline Date" in deadlines.columns:
    deadlines["Deadline Date"] = pd.to_datetime(deadlines["Deadline Date"], errors="coerce")

series_fields = [
    column
    for column in [
        "Series Code",
        "Conference Name",
        "Short Name",
        "Organizer",
        "Categories",
        "Official URL",
        "Cadence",
    ]
    if column in series.columns
]
series_small = series[series_fields].copy()
editions = editions.merge(series_small, on="Series Code", how="left", suffixes=("", "_series"))
deadlines = deadlines.merge(series_small, on="Series Code", how="left", suffixes=("", "_series"))

profile_key = str(st.query_params.get("profile", "") or "").strip().upper()
profile = None
watched_codes = []
if profile_key and AIRTABLE_ENABLED:
    try:
        profile = get_profile(profile_key)
        if profile:
            watched_codes = parse_list(profile["fields"].get("Watched Series", ""))
    except Exception as error:
        st.warning(f"Could not load this profile right now: {error}")

header_left, header_right = st.columns([4, 1])
with header_left:
    st.title(APP_TITLE)
    st.caption("One shared catalog; personalized watch lists for students, lab members, and colleagues.")
with header_right:
    st.success("Live Airtable") if AIRTABLE_ENABLED else st.info("Demo data")

if not AIRTABLE_ENABLED:
    missing = []
    if not AIRTABLE_BASE_ID:
        missing.append("AIRTABLE_BASE_ID")
    if not AIRTABLE_TOKEN:
        missing.append("AIRTABLE_TOKEN")
    st.warning(
        "This Streamlit deployment is not connected to Airtable, so personal watch lists and "
        "conference suggestions are disabled. Add the missing Streamlit secret(s): "
        + ", ".join(missing)
        + "."
    )

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
    all_categories = sorted(
        {
            category
            for value in series.get("Categories", pd.Series(dtype=str)).dropna()
            for category in parse_list(value)
        }
    )
    selected_categories = st.multiselect("Fields", all_categories)
    personal_only = (
        st.toggle("My watched conferences only", value=True) if watched_codes else False
    )


def series_passes(code, categories):
    if personal_only and code not in watched_codes:
        return False
    if not categories:
        return True
    row = series[series["Series Code"] == code]
    if row.empty:
        return False
    return bool(set(parse_list(row.iloc[0].get("Categories", ""))).intersection(categories))


today = pd.Timestamp(date.today())
deadline_cutoff = today + pd.Timedelta(days=horizon)

deadlines_view = deadlines.copy()
deadlines_view = deadlines_view[
    deadlines_view["Deadline Date"].notna()
    & (deadlines_view["Deadline Date"] >= today)
    & (deadlines_view["Deadline Date"] <= deadline_cutoff)
]
deadlines_view = deadlines_view[
    deadlines_view["Series Code"].map(lambda code: series_passes(code, selected_categories))
]
deadlines_view["Days Left"] = (deadlines_view["Deadline Date"] - today).dt.days
deadlines_view = deadlines_view.sort_values(["Deadline Date", "Short Name"], na_position="last")

editions_view = editions.copy()
if "End Date" in editions_view.columns:
    editions_view = editions_view[
        editions_view["End Date"].isna() | (editions_view["End Date"] >= today)
    ]
editions_view = editions_view[
    editions_view["Series Code"].map(lambda code: series_passes(code, selected_categories))
]
editions_view = editions_view.sort_values(["Start Date", "Conference Name"], na_position="last")

tab_deadlines, tab_meetings, tab_watch, tab_suggest = st.tabs(
    ["Upcoming deadlines", "Upcoming meetings", "My watch list", "Suggest a meeting"]
)

with tab_deadlines:
    st.subheader("Upcoming deadlines")
    if deadlines_view.empty:
        st.info("No confirmed deadlines match the current filters.")
    else:
        urgent = (deadlines_view["Days Left"] <= 30).sum()
        col1, col2, col3 = st.columns(3)
        col1.metric("Matching deadlines", len(deadlines_view))
        col2.metric("Within 30 days", int(urgent))
        col3.metric("Conferences represented", deadlines_view["Series Code"].nunique())

        deadline_columns = [
            column
            for column in [
                "Deadline Date",
                "Days Left",
                "Short Name",
                "Type",
                "Name",
                "Status",
                "Official Source URL",
                "Last Verified",
            ]
            if column in deadlines_view.columns
        ]
        display = deadlines_view[deadline_columns].copy()
        if "Deadline Date" in display:
            display["Deadline Date"] = display["Deadline Date"].dt.date
        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            column_config={"Official Source URL": st.column_config.LinkColumn("Official source")},
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
        meeting_columns = [
            column
            for column in [
                "Conference Name",
                "Start Date",
                "End Date",
                "City",
                "Region/Country",
                "Venue",
                "Edition Name",
                "Status",
                "Event URL",
            ]
            if column in editions_view.columns
        ]
        display = editions_view[meeting_columns].copy()
        display = display.rename(columns={"Conference Name": "Conference"})
        for column in ("Start Date", "End Date"):
            if column in display:
                display[column] = display[column].dt.date
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
        st.info(
            "This feature needs the Airtable credentials in Streamlit App settings → Secrets. "
            "The Airtable connection inside ChatGPT does not automatically configure the hosted app."
        )
        st.multiselect(
            "Preview a watch list",
            all_codes,
            default=defaults,
            format_func=lambda code: label_map.get(code, code),
            disabled=True,
        )
    elif profile:
        selected = st.multiselect(
            "Conferences to monitor",
            all_codes,
            default=[code for code in defaults if code in all_codes],
            format_func=lambda code: label_map.get(code, code),
        )
        if st.button("Save my watch list", type="primary"):
            try:
                update_profile(profile, selected)
                st.success("Watch list saved.")
                st.cache_data.clear()
                st.rerun()
            except Exception as error:
                st.error(f"Could not save: {error}")
        st.caption(f"Profile key: {profile_key}. Bookmark this page to return to your watch list.")
    else:
        st.write(
            "Create a lightweight profile. No password is required; the generated profile key "
            "becomes your private bookmark for editing this watch list."
        )
        with st.form("create_profile"):
            display_name = st.text_input(
                "Display name", placeholder="e.g., Yaxi / MSc student / Colleague"
            )
            role = st.selectbox(
                "Role",
                ["Faculty", "Postdoc", "Graduate student", "Undergraduate", "Staff", "Other"],
            )
            selected = st.multiselect(
                "Conferences to monitor",
                all_codes,
                format_func=lambda code: label_map.get(code, code),
            )
            submitted = st.form_submit_button("Create my watch list")
        if submitted:
            try:
                key, _ = create_profile(display_name, role, selected)
                st.query_params["profile"] = key
                st.success("Profile created.")
                st.rerun()
            except Exception as error:
                st.error(f"Could not create profile: {error}")

with tab_suggest:
    st.subheader("Suggest another conference")
    st.write(
        "Suggestions go to the shared catalog administrator for review before becoming visible to everyone."
    )
    if not AIRTABLE_ENABLED:
        st.info(
            "This feature needs the Airtable credentials in Streamlit App settings → Secrets. "
            "Once those two secrets are saved, this form becomes active automatically."
        )
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
                fields = {
                    "Suggestion ID": "SUG-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                    "Profile Key": profile_key or "",
                    "Conference Name": new_name.strip(),
                    "Official URL": new_url.strip(),
                    "Note": note.strip(),
                    "Status": "New",
                    "Created At": utc_now(),
                }
                try:
                    airtable_create(TABLES["suggestions"], fields)
                    st.success("Suggestion submitted.")
                except Exception as error:
                    st.error(f"Could not submit suggestion: {error}")

st.divider()
st.caption(
    "Dates marked Confirmed should be traceable to the linked official source. "
    "TBD means the organizer has not yet announced that item."
)
