import os
import time
import requests

BASE_URL = "https://api.notion.com/v1"
BUCKET_PARENT_ID = "24c34320-f7a5-8061-b65e-dea031a5dbfd"

_cache = {"pages": {}, "loaded_at": 0}


def _headers():
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def _get_blocks(page_id):
    blocks = []
    url = f"{BASE_URL}/blocks/{page_id}/children"
    params = {"page_size": 100}
    while True:
        resp = requests.get(url, headers=_headers(), params=params, timeout=8)
        data = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(f"Notion API error {resp.status_code}: {data.get('message', data)}")
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        params["start_cursor"] = data["next_cursor"]
    return blocks


def _block_text(block):
    block_type = block["type"]
    rich_text = block.get(block_type, {}).get("rich_text", [])
    return "".join(t["plain_text"] for t in rich_text)


def _get_location_pages():
    if time.time() - _cache["loaded_at"] > 3600:
        blocks = _get_blocks(BUCKET_PARENT_ID)
        _cache["pages"] = {
            b["child_page"]["title"].lower(): b["id"]
            for b in blocks if b["type"] == "child_page"
        }
        _cache["loaded_at"] = time.time()
    return _cache["pages"]


def _find_location(location):
    location_lower = location.lower()
    for name, page_id in _get_location_pages().items():
        if location_lower in name or name in location_lower:
            return page_id, name
    return None, None


def add_to_bucket_list(item, location):
    page_id, matched = _find_location(location)
    if not page_id:
        known = ", ".join(n.title() for n in _get_location_pages())
        return f"No bucket list for '{location}'. Known locations: {known}"

    try:
        blocks = _get_blocks(page_id)
    except RuntimeError as e:
        return str(e)

    for block in blocks:
        if block["type"] == "bulleted_list_item":
            if _block_text(block).strip().lower() == item.strip().lower():
                return f"'{item}' is already on the {matched.title()} list."

    new_block = {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": item}}]
        },
    }
    resp = requests.patch(
        f"{BASE_URL}/blocks/{page_id}/children",
        headers=_headers(),
        json={"children": [new_block]},
    )
    if resp.status_code == 200:
        return f"Added '{item}' to {matched.title()} bucket list ✓"
    return f"Error: {resp.json().get('message', 'unknown error')}"


def view_bucket_list(location):
    page_id, matched = _find_location(location)
    if not page_id:
        known = ", ".join(n.title() for n in _get_location_pages())
        return f"No bucket list for '{location}'. Known locations: {known}"

    try:
        blocks = _get_blocks(page_id)
    except RuntimeError as e:
        return str(e)

    items = [
        f"• {_block_text(b).strip()}"
        for b in blocks
        if b["type"] == "bulleted_list_item" and _block_text(b).strip()
    ]

    if not items:
        return f"{matched.title()} bucket list is empty."
    return f"{matched.title()}:\n" + "\n".join(items)


def list_locations():
    try:
        pages = _get_location_pages()
    except RuntimeError as e:
        return str(e)
    if not pages:
        return "No bucket list locations found."
    return "Bucket list locations:\n" + "\n".join(f"• {n.title()}" for n in sorted(pages))


def remove_from_bucket_list(item, location):
    page_id, matched = _find_location(location)
    if not page_id:
        return f"No bucket list for '{location}'."

    try:
        blocks = _get_blocks(page_id)
    except RuntimeError as e:
        return str(e)

    for block in blocks:
        if block["type"] == "bulleted_list_item":
            text = _block_text(block).strip()
            if item.lower() in text.lower():
                resp = requests.delete(f"{BASE_URL}/blocks/{block['id']}", headers=_headers())
                if resp.status_code == 200:
                    return f"Removed '{text}' from {matched.title()} ✓"
                return f"Error: {resp.json().get('message', 'unknown error')}"

    return f"'{item}' not found on the {matched.title()} list."
