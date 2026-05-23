import json
from .notion import add_item, remove_item, view_list, clear_list

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
    "laundry detergent": "Amazon",
    "floor cleaner": "Amazon",
    "paper towels": "Costco",
    "toilet paper": "Costco",
    "toilet brushes": "Costco",
    "dusters": "Costco",
    "water bottles": "Costco",
    "diapers": "Whole Foods",
    "baby wipes": "Amazon",
}

STORES = [
    "King Soopers", "Whole Foods", "Trader Joe's", "Indian/Asian/Arab Store",
    "Costco", "Sam's Club", "Walmart/Target", "Russian Store", "Mall", "Amazon", "Other",
]

SYSTEM_PROMPT_SECTION = f"""## Grocery
Item → Store mappings (match loosely — e.g. "oat milk" → Costco):
{json.dumps(ITEM_STORE_MAPPINGS, indent=2)}
Available stores: {', '.join(STORES)}
- If item matches a mapping, use that store automatically.
- If user specifies a store, use it.
- Otherwise, use best judgment — never ask, just add and say where.
- Multi-line messages: treat each line as a separate item, call add_item for each.
- "show list", "what's on my list" → view_list.
- Remove/delete requests → remove_item.
- "clear the list", "remove everything", "remove all" → ask for confirmation first: "This will remove all items. Reply YES to confirm." Only call clear_list after the user has confirmed with YES in this conversation."""

TOOLS = [
    {
        "name": "add_item",
        "description": "Add an item to a store's section on the Notion shopping list",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "store": {"type": "string", "description": "Must match one of the available stores"},
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
        "description": "View the shopping list, optionally filtered to one store",
        "input_schema": {
            "type": "object",
            "properties": {
                "store": {"type": "string", "description": "Optional — filter to this store only"},
            },
        },
    },
    {
        "name": "clear_list",
        "description": "Remove all items from the entire shopping list",
        "input_schema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "add_item": lambda inp: add_item(inp["item"], inp["store"]),
    "remove_item": lambda inp: remove_item(inp["item"], inp.get("store")),
    "view_list": lambda inp: view_list(inp.get("store")),
    "clear_list": lambda inp: clear_list(),
}
