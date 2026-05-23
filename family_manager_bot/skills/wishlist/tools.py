from .notion import add_to_wishlist, view_wishlist, remove_from_wishlist

SYSTEM_PROMPT_SECTION = """## Wishlist
Family wishlist pages per person: Gillian, Dalia, Mark, Asher.
- "add X to my wishlist" / "what's on my wishlist" → use the current sender's name from context.
- "add X to [person]'s wishlist" → add_to_wishlist with that person.
- "what's on [person]'s wishlist" / "show [person]'s list" → view_wishlist.
- "remove X from [person]'s wishlist" → remove_from_wishlist.
- If sender is not in the wishlist (e.g. Lena), say so instead of guessing."""

TOOLS = [
    {
        "name": "add_to_wishlist",
        "description": "Add an item to a family member's gift wishlist in Notion",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "person": {"type": "string", "description": "Gillian, Dalia, Mark, or Asher"},
            },
            "required": ["item", "person"],
        },
    },
    {
        "name": "view_wishlist",
        "description": "View a family member's gift wishlist",
        "input_schema": {
            "type": "object",
            "properties": {
                "person": {"type": "string"},
            },
            "required": ["person"],
        },
    },
    {
        "name": "remove_from_wishlist",
        "description": "Remove an item from a family member's wishlist",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "person": {"type": "string"},
            },
            "required": ["item", "person"],
        },
    },
]

HANDLERS = {
    "add_to_wishlist": lambda inp: add_to_wishlist(inp["item"], inp["person"]),
    "view_wishlist": lambda inp: view_wishlist(inp["person"]),
    "remove_from_wishlist": lambda inp: remove_from_wishlist(inp["item"], inp["person"]),
}
