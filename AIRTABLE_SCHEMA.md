# Airtable schema

Create one Airtable base named **Conference Tracker** with these five tables. Import the three CSV files in `data/` for the first three tables.

## 1. Conference Series
Primary field: **Series Code** (single line text)

Fields:
- Series Code — single line text
- Conference Name — single line text
- Short Name — single line text
- Organizer — single line text
- Categories — long text (comma-separated is simplest for the free pilot)
- Official URL — URL
- Cadence — single select or single line text
- Active — checkbox
- Notes — long text

## 2. Conference Editions
Primary field: **Edition ID**

Fields:
- Edition ID — single line text
- Series Code — single line text
- Year — number
- Edition Name — single line text
- Start Date — date
- End Date — date
- City — single line text
- Region/Country — single line text
- Venue — single line text
- Event URL — URL
- Status — single select: Confirmed / Partial / TBD / Cancelled
- Last Verified — date

## 3. Deadlines
Primary field: **Deadline ID**

Fields:
- Deadline ID — single line text
- Edition ID — single line text
- Series Code — single line text
- Type — single select (Abstract, Symposium proposal, Award, Travel grant, Registration, Accommodation, Other)
- Name — single line text
- Deadline Date — date
- Status — single select: Confirmed / Partial / TBD
- Official Source URL — URL
- Last Verified — date
- Notes — long text

## 4. Profiles
Primary field: **Profile Key**

Fields:
- Profile Key — single line text
- Display Name — single line text
- Role — single select
- Watched Series — long text
- Created At — date/time (include time)
- Updated At — date/time (include time)

The app stores conference codes as a comma-separated list in **Watched Series**. One Airtable record therefore represents one person's whole watch list, which conserves free-tier records.

## 5. Suggestions
Primary field: **Suggestion ID**

Fields:
- Suggestion ID — single line text
- Profile Key — single line text
- Conference Name — single line text
- Official URL — URL
- Note — long text
- Status — single select: New / Reviewing / Accepted / Declined
- Created At — date/time

## Airtable personal access token
Create a personal access token restricted to this base. It needs record read access for Conference Series, Conference Editions, and Deadlines, and read/write access for Profiles and Suggestions.

Do **not** put the token into GitHub. Put it only in Streamlit Community Cloud -> App settings -> Secrets.
