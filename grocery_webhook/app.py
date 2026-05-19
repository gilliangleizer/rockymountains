import os
import json
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import anthropic
from dotenv import load_dotenv
from notion_helper import add_item, remove_item, view_list

load_dotenv()

app = Flask(__name__)
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
- If neither applies, reply asking which store. Do not call a tool.
- "what's on my list", "show list", "list" → call view_list.
- Remove/delete requests → call remove_item.
- Add requests with a known store → call add_item.
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
        "description": "View the current shopping list organized by store",
        "input_schema": {"type": "object", "properties": {}},
    },
]


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.form.get("Body", "").strip()

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        tools=TOOLS,
        messages=[{"role": "user", "content": body}],
    )

    reply = "Try: 'add milk', 'remove eggs', or 'show list'."

    for block in response.content:
        if block.type == "tool_use":
            if block.name == "add_item":
                reply = add_item(block.input["item"], block.input["store"])
            elif block.name == "remove_item":
                reply = remove_item(block.input["item"], block.input.get("store"))
            elif block.name == "view_list":
                reply = view_list()
        elif block.type == "text" and block.text.strip():
            reply = block.text.strip()

    twiml = MessagingResponse()
    twiml.message(reply)
    return str(twiml), 200, {"Content-Type": "text/xml"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, port=port)
