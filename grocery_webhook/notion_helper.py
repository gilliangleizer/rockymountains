import os
import re
import requests

PAGE_ID = "fb227610-45cc-46c4-9a84-55cc25536e0a"
BASE_URL = "https://api.notion.com/v1"


def _headers():
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def _get_page_blocks():
    blocks = []
    url = f"{BASE_URL}/blocks/{PAGE_ID}/children"
    params = {"page_size": 100}
    while True:
        resp = requests.get(url, headers=_headers(), params=params)
        data = resp.json()
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        params["start_cursor"] = data["next_cursor"]
    return blocks


def _block_text(block):
    block_type = block["type"]
    rich_text = block.get(block_type, {}).get("rich_text", [])
    return "".join(t["plain_text"] for t in rich_text)


def _stores_match(block_text, store_name):
    if block_text.lower() == store_name.lower():
        return True
    # Fall back to checking all significant words appear (handles Notion text corruption)
    words = [w for w in re.split(r'[^a-z]+', store_name.lower()) if len(w) > 2]
    block_lower = block_text.lower()
    return bool(words) and all(w in block_lower for w in words)


def _find_insert_position(blocks, store_name):
    """Returns block ID to insert after for the given store section."""
    heading_idx = None
    for i, block in enumerate(blocks):
        if block["type"] == "heading_2" and _stores_match(_block_text(block), store_name):
            heading_idx = i
            break

    if heading_idx is None:
        return None

    insert_after_id = blocks[heading_idx]["id"]
    for i in range(heading_idx + 1, len(blocks)):
        if blocks[i]["type"] == "heading_2":
            break
        insert_after_id = blocks[i]["id"]

    return insert_after_id


def add_item(item, store):
    blocks = _get_page_blocks()
    insert_after_id = _find_insert_position(blocks, store)

    if not insert_after_id:
        return f"Store '{store}' not found."

    new_block = {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": item}}]
        },
    }

    resp = requests.patch(
        f"{BASE_URL}/blocks/{PAGE_ID}/children",
        headers=_headers(),
        json={"children": [new_block], "after": insert_after_id},
    )

    if resp.status_code == 200:
        return f"Added {item} to {store} ✓"
    return f"Error: {resp.json().get('message', 'unknown error')}"


def remove_item(item, store=None):
    blocks = _get_page_blocks()
    current_store = None

    for block in blocks:
        if block["type"] == "heading_2":
            current_store = _block_text(block)
        elif block["type"] == "bulleted_list_item":
            text = _block_text(block)
            store_match = store is None or (current_store and _stores_match(current_store, store))
            if item.lower() in text.lower() and store_match:
                resp = requests.delete(f"{BASE_URL}/blocks/{block['id']}", headers=_headers())
                if resp.status_code == 200:
                    return f"Removed '{text}' from {current_store} ✓"
                return f"Error: {resp.json().get('message', 'unknown error')}"

    return f"'{item}' not found on the list."


def view_list():
    blocks = _get_page_blocks()
    current_store = None
    sections = {}

    for block in blocks:
        if block["type"] == "heading_2":
            current_store = _block_text(block)
            sections[current_store] = []
        elif block["type"] == "bulleted_list_item" and current_store:
            text = _block_text(block).strip()
            if text:
                sections[current_store].append(text)

    lines = []
    for store, items in sections.items():
        if items:
            lines.append(f"{store}:")
            lines.extend(f"  • {item}" for item in items)

    return "\n".join(lines) if lines else "Your shopping list is empty!"
