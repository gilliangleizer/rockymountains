import os
import requests

BASE_URL = "https://api.notion.com/v1"

WISHLIST_PAGES = {
    "gillian": "3cc46a83-e8b3-430f-ac5e-9bf8f5a30d97",
    "dalia": "3dbb2c8a-7476-432c-8341-70fd4172978c",
    "mark": "be6aff962a5f487c80dec5be28f48d9e",
    "asher": "26a34320-f7a5-804e-a42b-c1980b97565f",
}


def _headers():
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def _find_person(person):
    person_lower = person.lower()
    for name, page_id in WISHLIST_PAGES.items():
        if person_lower in name or name in person_lower:
            return page_id, name
    return None, None


def _get_blocks(page_id):
    blocks = []
    url = f"{BASE_URL}/blocks/{page_id}/children"
    params = {"page_size": 100}
    while True:
        resp = requests.get(url, headers=_headers(), params=params)
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


def add_to_wishlist(item, person):
    page_id, matched = _find_person(person)
    if not page_id:
        return f"No wishlist for '{person}'. Known: {', '.join(WISHLIST_PAGES.keys())}"

    try:
        blocks = _get_blocks(page_id)
    except RuntimeError as e:
        return str(e)

    for block in blocks:
        if block["type"] == "bulleted_list_item":
            if _block_text(block).strip().lower() == item.strip().lower():
                return f"'{item}' is already on {matched.title()}'s wishlist."

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
        return f"Added '{item}' to {matched.title()}'s wishlist ✓"
    return f"Error: {resp.json().get('message', 'unknown error')}"


def view_wishlist(person):
    page_id, matched = _find_person(person)
    if not page_id:
        return f"No wishlist for '{person}'. Known: {', '.join(WISHLIST_PAGES.keys())}"

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
        return f"{matched.title()}'s wishlist is empty."
    return f"{matched.title()}'s wishlist:\n" + "\n".join(items)


def remove_from_wishlist(item, person):
    page_id, matched = _find_person(person)
    if not page_id:
        return f"No wishlist for '{person}'."

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
                    return f"Removed '{text}' from {matched.title()}'s wishlist ✓"
                return f"Error: {resp.json().get('message', 'unknown error')}"

    return f"'{item}' not found on {matched.title()}'s wishlist."
