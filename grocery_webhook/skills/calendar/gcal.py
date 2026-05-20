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


def _event_matches_person(event, person):
    person_lower = person.lower()
    text = " ".join([
        event.get("summary", ""),
        event.get("description", ""),
        event.get("location", ""),
    ]).lower()
    return person_lower in text or "family" in text


def view_events(start_date=None, end_date=None, person=None):
    try:
        service = _get_service()
    except Exception as e:
        return f"Calendar auth error: {e}"

    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)

    if start_date:
        time_min = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0, tzinfo=tz)
    else:
        time_min = now

    if end_date and end_date != start_date:
        time_max = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=tz)
    else:
        # Default: end of start day, or 7 days from now if no start given
        if start_date:
            time_max = time_min + timedelta(days=1)
        else:
            time_max = now + timedelta(hours=24)

    time_min = time_min.isoformat()
    time_max = time_max.isoformat()

    result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=time_min,
        timeMax=time_max,
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    if person:
        events = [e for e in events if _event_matches_person(e, person)]

    if not events:
        label = f"{person.title()}'s " if person else ""
        return f"No {label}events in that time range."

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
            end_dt = start_dt + timedelta(minutes=30)
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

    event_body["attendees"] = [{"email": "izrailev.mark@gmail.com"}]

    service.events().insert(calendarId=CALENDAR_ID, body=event_body, sendUpdates="all").execute()
    return f"Added '{title}' to calendar ✓"
