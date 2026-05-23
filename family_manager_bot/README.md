# Family Manager Bot

A WhatsApp assistant for the Gleizer-Izrailev family. Send a text and it manages your grocery list, wishlists, calendar, bucket list, and home thermostat — backed by Notion, Google Calendar, and Seam.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Messaging | WhatsApp via Twilio |
| AI | Claude Sonnet (Anthropic API) |
| Web server | Flask + Gunicorn |
| Hosting | Render |
| Data (grocery, wishlists, bucket list) | Notion API |
| Data (calendar) | Google Calendar API v3 |
| Data (thermostat) | Seam API (Ecobee) |
| Language | Python 3.9+ |

---

## How It Works

1. A family member sends a WhatsApp message.
2. Twilio receives it and forwards it as an HTTP POST to `/webhook` on Render.
3. Flask handles the request. It checks the sender's phone number against an allowlist, then looks up their name and timezone.
4. The message (plus the last 10 messages of conversation history) is sent to Claude with a system prompt describing all available tools.
5. Claude decides which tool to call (e.g. `add_item`, `view_events`) and returns a `tool_use` response.
6. The server executes the tool — hitting the Notion or Google Calendar API — and sends the result back to Claude.
7. Claude formats a friendly reply, which is sent back to the user via Twilio TwiML.

The system prompt is cached with Anthropic's prompt caching to reduce latency and cost.

---

## Project Structure

```
family_manager_bot/
├── app.py                  # Flask app, webhook handler, Claude orchestration
├── requirements.txt
├── skills/
│   ├── grocery/
│   │   ├── tools.py        # Tool definitions, handlers, system prompt section
│   │   └── notion.py       # Notion API calls for the shopping list
│   ├── wishlist/
│   │   ├── tools.py
│   │   └── notion.py       # Per-person gift wishlist pages
│   ├── calendar/
│   │   ├── tools.py
│   │   └── gcal.py         # Google Calendar API calls
│   ├── bucketlist/
│   │   ├── tools.py
│   │   └── notion.py       # Per-location bucket list pages
│   └── thermostat/
│       ├── tools.py
│       └── seam.py         # Seam API calls for Ecobee thermostat
```

Each skill exports three things that `app.py` combines:
- `TOOLS` — Claude tool definitions (JSON schemas)
- `HANDLERS` — functions that execute each tool
- `SYSTEM_PROMPT_SECTION` — natural language instructions for Claude

---

## Capabilities

### Grocery List
Backed by a single Notion page organised by store.

- `add milk` → adds milk to the right store (auto-assigned via item→store mappings)
- `add coffee to Whole Foods` → use a specific store
- `show my list` / `show the Costco list`
- `remove milk`
- `clear the list` (requires YES confirmation)

**Stores:** King Soopers, Whole Foods, Trader Joe's, Indian/Asian/Arab Store, Costco, Sam's Club, Walmart/Target, Russian Store, Mall, Amazon, Other

### Gift Wishlists
One Notion page per person under the "Gift Wish Lists" parent. New people are picked up automatically within 1 hour.

- `add boots to my wishlist`
- `add headphones to Mark's wishlist`
- `what's on Dalia's wishlist`
- `remove boots from my wishlist`

**Family members:** Gillian, Mark, Dalia, Asher (and anyone added as a new page)

### Google Calendar
Reads and writes to the primary Google Calendar. All new events include Mark as a guest.

- `what's on my calendar tomorrow`
- `show Mark's schedule this week`
- `add dentist appointment Friday at 2pm`
- `add Asher's party tomorrow 8:30-9am`

Default event duration is 30 minutes. Supports time ranges (e.g. `8:30-9a`).

### Bucket List
One Notion page per location under "Bucket Lists - Places to Go, See, Eat". New locations are picked up automatically within 1 hour.

- `add Dishoom to London`
- `show my Japan list`
- `what locations do I have`
- `remove Nobu from Japan`

### Thermostat
Controls the home Ecobee thermostat via the Seam API.

- `what's the temperature at home` → current temp, humidity, mode, and setpoints
- `set heat to 70` / `set it to 72 degrees`
- `set to cool only` / `set to auto` / `turn off the heat`

---

## Configuration

### Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `NOTION_TOKEN` | Notion integration token |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_REFRESH_TOKEN` | Google OAuth refresh token |
| `SEAM_API_KEY` | Seam API key (for Ecobee thermostat) |
| `SEAM_DEVICE_ID` | Optional — pin to a specific thermostat device ID (auto-discovers if omitted) |
| `ALLOWED_NUMBERS` | Comma-separated phone numbers allowed to use the bot (e.g. `+13038757999,+12018870125`) |
| `PORT` | Server port (default: 5001) |

### Phone → Person Mapping
Defined in `app.py`:
- `+1-303-875-7999` → Mark (America/Denver)
- `+1-201-887-0125` → Gillian (America/New_York)
- `+1-404-358-0862` → Lena (America/New_York)

---

## Adding a New Skill

1. Create `skills/<name>/` with `__init__.py`, `tools.py`, and an API module.
2. Define `TOOLS`, `HANDLERS`, and `SYSTEM_PROMPT_SECTION` in `tools.py`.
3. Import and wire up in `app.py` (add to `TOOLS`, `TOOL_HANDLERS`, and `SYSTEM_PROMPT`).

---

## Keep-Alive
A `/health` endpoint is pinged every 10 minutes by cron-job.org to prevent Render's free tier from spinning the service down.
