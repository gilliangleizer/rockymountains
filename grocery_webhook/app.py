import os
import json
from collections import defaultdict
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import anthropic
from dotenv import load_dotenv
from notion_helper import add_item, remove_item, view_list

load_dotenv()

app = Flask(__name__)
conversations = defaultdict(list)  # phone number → message history
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

ITEM_STORE_MAPPINGS = {
    "milk": "Costco",
    "eggs": "Costco",
    "meat sticks": "Costco",
    "cheese sticks": "Costco",
    "baby tomatoes": "Costco",
    "asian ingredients": "Indian/Asian/Arab Store",
    "spices": "Indian/Asian/Arab Store",
    "coffee": "Whole Foods",
    "decaf coffee": "Whole Foods",
    "buckwheat": "Russian Store",
}

STORES = [
    "King Soopers", "Whole Foods", "Trader Joe's", "Indian/Asian/Arab Store",
    "Costco", "Sam's Club", "Walmart/Target", "Russian Store", "Mall", "Amazon", "Other",
]

SYSTEM_PROMPT = f"""You are a grocery list assistant that processes SMS/WhatsApp messages.

Item → Store mappings (apply automatically, match loosely — e.g. "oat milk" → Costco):
{json.dumps(ITEM_STORE_MAPPINGS, indent=2)}

Available stores: {', '.join(STORES)}

Rules:
- If the item matches a mapping (even loosely), use that store — do NOT ask.
- If the user specifies a store (e.g. "add salsa to Trader Joe's"), use it.
- If neither applies, use your best judgment based on the item's name and category to pick the most appropriate store from the list. Never ask — just add it and say which store you chose.
- "what's on my list", "show list", "list" → call view_list.
- Remove/delete requests → call remove_item.
- Add requests with a known store → call add_item.
- If the message has multiple lines, treat each line as a separate item. Call add_item for each line that has a known store. For lines with no known store, ask about them all at once at the end.
- Accept messages in any language. Translate item names to English before adding them to the list.
- Reply in the same language the user wrote in.
- Keep replies short."""

TOOLS = [
    {
        "name": "add_item",
        "description": "Add an item to a store's section on the Notion shopping list",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "store": {"type": "string", "description": "Must exactly match one of the available stores"},
            },
            "required": ["item", "store"],
        },
    },
    {
        "name": "remove_item",
        "description": "Remove an item from the Notion shopping list",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "store": {"type": "string", "description": "Optional — omit to search all stores"},
            },
            "required": ["item"],
        },
    },
    {
        "name": "view_list",
        "description": "View the current shopping list. Optionally filter to a single store.",
        "input_schema": {
            "type": "object",
            "properties": {
                "store": {"type": "string", "description": "Optional — only show items for this store"},
            },
        },
    },
]


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "unknown")

    history = conversations[from_number]
    history.append({"role": "user", "content": body})

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        tools=TOOLS,
        messages=history,
    )

    reply = "Try: 'add milk', 'remove eggs', or 'show list'."

    if response.stop_reason == "tool_use":
        results = []
        for tool_block in (b for b in response.content if b.type == "tool_use"):
            if tool_block.name == "add_item":
                results.append(add_item(tool_block.input["item"], tool_block.input["store"]))
            elif tool_block.name == "remove_item":
                results.append(remove_item(tool_block.input["item"], tool_block.input.get("store")))
            elif tool_block.name == "view_list":
                results.append(view_list(tool_block.input.get("store")))
        reply = "\n".join(results)
    else:
        text = next((b.text for b in response.content if b.type == "text"), "")
        if text.strip():
            reply = text.strip()

    history.append({"role": "assistant", "content": [{"type": "text", "text": reply}]})

    # Keep last 10 messages to avoid token bloat
    if len(history) > 10:
        conversations[from_number] = history[-10:]

    twiml = MessagingResponse()
    twiml.message(reply)
    return str(twiml), 200, {"Content-Type": "text/xml"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)
