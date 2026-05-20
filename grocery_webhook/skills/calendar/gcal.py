import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

CALENDAR_ID = "primary"
TIMEZONE = "America/Denver"
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _format_dt(dt_str):
    try:
        if "T" in dt_str:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            dt_local = dt.astimezone(ZoneInfo(TIMEZONE))
            return dt_local.strftime("%a %b %-d, %-I:%M %p")
        else:
            dt = datetime.strptime(dt_str, "%Y-%m-%d")
            return dt.strftime("%a %b %-d")
    except Exception:
        return dt_str


def view_events(start_date=None, end_date=None):
    try:
        service = _get_service()
    except Exception as e:
        return f"Calendar auth error: {e}"

    now = datetime.now(ZoneInfo(TIMEZONE))
    time_min = datetime.fromisoformat(start_date).isoformat() + "Z" if start_date else now.isoformat()
    time_max = datetime.fromisoformat(end_date).isoformat() + "Z" if end_date else (now + timedelta(days=7)).isoformat()

    result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=time_min,
        timeMax=time_max,
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    if not events:
        return "No events in that time range."

    lines = []
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date", ""))
        lines.append(f"• {_format_dt(start)}: {event.get('summary', 'No title')}")

    return "\n".join(lines)


def add_event(title, date, time=None, description=None):
    try:
        service = _get_service()
    except Exception as e:
        return f"Calendar auth error: {e}"

    if time:
        try:
            start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(TIMEZONE))
            end_dt = start_dt + timedelta(hours=1)
            event_body = {
                "summary": title,
                "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE},
            }
        except Exception as e:
            return f"Couldn't parse '{date} {time}': {e}"
    else:
        event_body = {
            "summary": title,
            "start": {"date": date},
            "end": {"date": date},
        }

    if description:
        event_body["description"] = description

    service.events().insert(calendarId=CALENDAR_ID, body=event_body).execute()
    return f"Added '{title}' to calendar ✓"
