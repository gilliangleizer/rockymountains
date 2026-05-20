from .gcal import view_events, add_event

SYSTEM_PROMPT_SECTION = """## Calendar
Google Calendar integration. Timezone: America/Denver (Mountain Time).
- "what's on my calendar", "show my schedule", "what's happening this week/today/tomorrow" → view_events.
- "what's on [person]'s calendar tomorrow" → view_events with person set, filters events containing that name or "Family".
- "add [event] on [date] at [time]" → add_event.
- For view_events: convert relative dates to ISO (YYYY-MM-DD) using today's date.
- For add_event: date = YYYY-MM-DD, time = HH:MM in 24h format (omit for all-day events)."""

TOOLS = [
    {
        "name": "view_events",
        "description": "View upcoming Google Calendar events",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "ISO date YYYY-MM-DD, defaults to today"},
                "end_date": {"type": "string", "description": "ISO date YYYY-MM-DD, defaults to 7 days from now"},
                "person": {"type": "string", "description": "Optional — filter events matching this person's name or 'Family'"},
            },
        },
    },
    {
        "name": "add_event",
        "description": "Add an event to Google Calendar",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "time": {"type": "string", "description": "24h time HH:MM — omit for all-day"},
                "description": {"type": "string", "description": "Optional notes"},
            },
            "required": ["title", "date"],
        },
    },
]

HANDLERS = {
    "view_events": lambda inp: view_events(inp.get("start_date"), inp.get("end_date"), inp.get("person")),
    "add_event": lambda inp: add_event(inp["title"], inp["date"], inp.get("time"), inp.get("description")),
}
