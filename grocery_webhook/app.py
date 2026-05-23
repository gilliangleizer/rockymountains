import os
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import anthropic
from dotenv import load_dotenv

from skills.grocery.tools import TOOLS as GROCERY_TOOLS, HANDLERS as GROCERY_HANDLERS, SYSTEM_PROMPT_SECTION as GROCERY_PROMPT
from skills.wishlist.tools import TOOLS as WISHLIST_TOOLS, HANDLERS as WISHLIST_HANDLERS, SYSTEM_PROMPT_SECTION as WISHLIST_PROMPT
from skills.calendar.tools import TOOLS as CALENDAR_TOOLS, HANDLERS as CALENDAR_HANDLERS, SYSTEM_PROMPT_SECTION as CALENDAR_PROMPT
from skills.bucketlist.tools import TOOLS as BUCKET_TOOLS, HANDLERS as BUCKET_HANDLERS, SYSTEM_PROMPT_SECTION as BUCKET_PROMPT

load_dotenv()

app = Flask(__name__)
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
conversations = defaultdict(list)

TOOLS = GROCERY_TOOLS + WISHLIST_TOOLS + CALENDAR_TOOLS + BUCKET_TOOLS
TOOL_HANDLERS = {**GROCERY_HANDLERS, **WISHLIST_HANDLERS, **CALENDAR_HANDLERS, **BUCKET_HANDLERS}

SYSTEM_PROMPT = f"""You are a family assistant accessible via WhatsApp. You manage the grocery list, family wishlists, Google Calendar, and a location-based bucket list.

{GROCERY_PROMPT}

{WISHLIST_PROMPT}

{CALENDAR_PROMPT}

{BUCKET_PROMPT}

## General
- Accept any language. Reply in the user's language.
- ALWAYS pass item names to tools in English, regardless of the user's language. Translate before calling any tool.
- If the user says "change that to X" or "move that to X", use conversation history to identify the last item, remove it from its current location, and add it to the new one.
- Keep replies short and friendly.
- If the request is unclear or outside your capabilities, say so briefly and remind the user what you can help with (grocery list, wishlists, calendar)."""


ALLOWED_NUMBERS = [n.strip() for n in os.environ.get("ALLOWED_NUMBERS", "").split(",") if n.strip()]

PHONE_ALIASES = {
    "whatsapp:+13038757999": "Mark",
    "whatsapp:+12018870125": "Gillian",
    "whatsapp:+14043580862": "Lena",
}

PHONE_TIMEZONES = {
    "whatsapp:+13038757999": "America/Denver",
    "whatsapp:+12018870125": "America/New_York",
    "whatsapp:+14043580862": "America/New_York",
}


@app.route("/health")
def health():
    return "ok", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "unknown")

    normalized = from_number.removeprefix("whatsapp:")
    if ALLOWED_NUMBERS and normalized not in ALLOWED_NUMBERS and from_number not in ALLOWED_NUMBERS:
        return str(MessagingResponse()), 200, {"Content-Type": "text/xml"}

    history = conversations[from_number]
    history.append({"role": "user", "content": body})

    tz = ZoneInfo(PHONE_TIMEZONES.get(from_number, "America/Denver"))
    today_str = datetime.now(tz).strftime("%A, %B %-d, %Y")
    sender_name = PHONE_ALIASES.get(from_number, "Unknown")

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[
            {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"Today is {today_str}. You are talking to {sender_name}."},
        ],
        tools=TOOLS,
        messages=history,
    )

    reply = "Try: 'add milk', 'add boots to my wishlist', or 'show my calendar'."

    if response.stop_reason == "tool_use":
        history.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tool_block in (b for b in response.content if b.type == "tool_use"):
            handler = TOOL_HANDLERS.get(tool_block.name)
            if handler:
                try:
                    result = handler(tool_block.input)
                except Exception as e:
                    result = f"Error running {tool_block.name}: {e}"
            else:
                result = f"Unknown tool: {tool_block.name}"
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                "content": result,
            })

        history.append({"role": "user", "content": tool_results})
        followup = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=[
                {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": f"Today is {today_str}. You are talking to {sender_name}."},
            ],
            tools=TOOLS,
            messages=history,
        )
        text = next((b.text for b in followup.content if b.type == "text"), "")
        if text.strip():
            reply = text.strip()
    else:
        text = next((b.text for b in response.content if b.type == "text"), "")
        if text.strip():
            reply = text.strip()

    history.append({"role": "assistant", "content": [{"type": "text", "text": reply}]})
    if len(history) > 10:
        conversations[from_number] = history[-10:]

    twiml = MessagingResponse()
    twiml.message(reply)
    return str(twiml), 200, {"Content-Type": "text/xml"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)
