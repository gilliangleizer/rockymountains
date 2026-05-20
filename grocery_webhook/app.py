import os
from collections import defaultdict
from datetime import date
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import anthropic
from dotenv import load_dotenv

from skills.grocery.tools import TOOLS as GROCERY_TOOLS, HANDLERS as GROCERY_HANDLERS, SYSTEM_PROMPT_SECTION as GROCERY_PROMPT
from skills.wishlist.tools import TOOLS as WISHLIST_TOOLS, HANDLERS as WISHLIST_HANDLERS, SYSTEM_PROMPT_SECTION as WISHLIST_PROMPT
from skills.calendar.tools import TOOLS as CALENDAR_TOOLS, HANDLERS as CALENDAR_HANDLERS, SYSTEM_PROMPT_SECTION as CALENDAR_PROMPT

load_dotenv()

app = Flask(__name__)
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
conversations = defaultdict(list)

TOOLS = GROCERY_TOOLS + WISHLIST_TOOLS + CALENDAR_TOOLS
TOOL_HANDLERS = {**GROCERY_HANDLERS, **WISHLIST_HANDLERS, **CALENDAR_HANDLERS}

SYSTEM_PROMPT = f"""You are a family assistant accessible via WhatsApp. You manage the grocery list, family wishlists, and Google Calendar.

{GROCERY_PROMPT}

{WISHLIST_PROMPT}

{CALENDAR_PROMPT}

## General
- Accept any language. Translate item names to English. Reply in the user's language.
- If the user says "change that to X" or "move that to X", use conversation history to identify the last item, remove it from its current location, and add it to the new one.
- Keep replies short and friendly."""


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "unknown")

    history = conversations[from_number]
    history.append({"role": "user", "content": body})

    today_str = date.today().strftime("%A, %B %-d, %Y")

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[
            {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"Today is {today_str}."},
        ],
        tools=TOOLS,
        messages=history,
    )

    reply = "Try: 'add milk', 'add boots to my wishlist', or 'show my calendar'."

    if response.stop_reason == "tool_use":
        results = []
        for tool_block in (b for b in response.content if b.type == "tool_use"):
            handler = TOOL_HANDLERS.get(tool_block.name)
            if handler:
                try:
                    results.append(handler(tool_block.input))
                except Exception as e:
                    results.append(f"Error running {tool_block.name}: {e}")
        reply = "\n".join(results)
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
