from .notion import add_to_bucket_list, view_bucket_list, list_locations, remove_from_bucket_list

SYSTEM_PROMPT_SECTION = """## Bucket List
Location-based bucket list of restaurants, places, and experiences to try.
- "add X to [location]" / "add X to my [location] list" → add_to_bucket_list
- "show my [location] list" / "what's on my [location] list" → view_bucket_list
- "what locations do I have" / "show all my lists" → list_locations
- "remove X from [location]" → remove_from_bucket_list
- If location is ambiguous or not found, call list_locations and ask the user to clarify."""

TOOLS = [
    {
        "name": "add_to_bucket_list",
        "description": "Add a restaurant, place, or experience to a location's bucket list",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "location": {"type": "string", "description": "e.g. Japan, Paris, Denver"},
            },
            "required": ["item", "location"],
        },
    },
    {
        "name": "view_bucket_list",
        "description": "View the bucket list for a specific location",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
            },
            "required": ["location"],
        },
    },
    {
        "name": "list_locations",
        "description": "List all available bucket list locations",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "remove_from_bucket_list",
        "description": "Remove an item from a location's bucket list",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "location": {"type": "string"},
            },
            "required": ["item", "location"],
        },
    },
]

HANDLERS = {
    "add_to_bucket_list": lambda inp: add_to_bucket_list(inp["item"], inp["location"]),
    "view_bucket_list": lambda inp: view_bucket_list(inp["location"]),
    "list_locations": lambda inp: list_locations(),
    "remove_from_bucket_list": lambda inp: remove_from_bucket_list(inp["item"], inp["location"]),
}
