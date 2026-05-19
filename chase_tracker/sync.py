"""
Fetch transactions from both Chase cards and sync to Google Sheets.
Run: python chase_tracker/sync.py
"""
import os
import datetime
from dotenv import load_dotenv
import plaid
from plaid.api import plaid_api
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
import gspread

DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(DIR, ".env"))

PLAID_CLIENT_ID = os.environ["PLAID_CLIENT_ID"]
PLAID_SECRET = os.environ["PLAID_SECRET"]
PLAID_ENV = os.getenv("PLAID_ENV", "development")
ACCESS_TOKENS = [os.environ["PLAID_ACCESS_TOKEN_1"], os.environ["PLAID_ACCESS_TOKEN_2"]]
CARD_NAMES = [os.getenv("CARD_1_NAME", "Card 1"), os.getenv("CARD_2_NAME", "Card 2")]
SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
DAYS_TO_FETCH = int(os.getenv("DAYS_TO_FETCH", "90"))

CREDENTIALS_FILE = os.path.join(DIR, "credentials.json")
TOKEN_FILE = os.path.join(DIR, "token.json")

HEADERS = ["Date", "Description", "Amount", "Card", "Auto Category", "Override", "Final Category", "Transaction ID"]

# ── Plaid ──────────────────────────────────────────────────────────────────────

def make_plaid_client():
    env_map = {
        "sandbox": plaid.Environment.Sandbox,
        "development": plaid.Environment.Development,
    }
    config = plaid.Configuration(
        host=env_map.get(PLAID_ENV, plaid.Environment.Development),
        api_key={"clientId": PLAID_CLIENT_ID, "secret": PLAID_SECRET},
    )
    return plaid_api.PlaidApi(plaid.ApiClient(config))


def fetch_transactions(client, access_token, card_name):
    end = datetime.date.today()
    start = end - datetime.timedelta(days=DAYS_TO_FETCH)
    req = TransactionsGetRequest(
        access_token=access_token,
        start_date=start,
        end_date=end,
        options=TransactionsGetRequestOptions(count=500),
    )
    resp = client.transactions_get(req)
    return [
        {
            "id": t["transaction_id"],
            "date": str(t["date"]),
            "description": t["name"],
            "amount": round(float(t["amount"]), 2),  # positive = money spent
            "card": card_name,
        }
        for t in resp["transactions"]
        if not t.get("pending", False)  # skip pending transactions
    ]


# ── Categorization ─────────────────────────────────────────────────────────────

def load_rules(sheet):
    try:
        ws = sheet.worksheet("Rules")
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet("Rules", rows=200, cols=2)
        ws.update("A1:B1", [["Keyword", "Category"]])
        ws.format("A1:B1", {"textFormat": {"bold": True}})
        print("  Created 'Rules' tab — add keyword→category rows there.")
        return []

    rows = ws.get_all_values()
    return [
        (row[0].strip().lower(), row[1].strip())
        for row in rows[1:]
        if len(row) >= 2 and row[0].strip() and row[1].strip()
    ]


def categorize(description, rules):
    desc_lower = description.lower()
    for keyword, category in rules:
        if keyword in desc_lower:
            return category
    return "Uncategorized"


# ── Google Sheets ──────────────────────────────────────────────────────────────

def sync_transactions(sheet, all_transactions, rules):
    try:
        ws = sheet.worksheet("Transactions")
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet("Transactions", rows=2000, cols=8)

    # Read existing rows — preserve any Override values the user has set
    existing_data = ws.get_all_values()
    existing_overrides = {}  # transaction_id -> override value
    if len(existing_data) > 1:
        for row in existing_data[1:]:
            if len(row) >= 8 and row[7]:
                existing_overrides[row[7]] = row[5] if len(row) > 5 else ""

    # Build rows
    rows = []
    for t in all_transactions:
        auto_cat = categorize(t["description"], rules)
        override = existing_overrides.get(t["id"], "")
        final_cat = override if override else auto_cat
        rows.append([
            t["date"], t["description"], t["amount"], t["card"],
            auto_cat, override, final_cat, t["id"]
        ])

    # Sort newest first
    rows.sort(key=lambda r: r[0], reverse=True)

    # Write to sheet
    ws.clear()
    ws.update("A1:H1", [HEADERS])
    if rows:
        ws.update(f"A2:H{1 + len(rows)}", rows)

    # Formatting
    ws.format("A1:H1", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8}, "foregroundColor": {"red": 1, "green": 1, "blue": 1}})
    ws.freeze(rows=1)

    # Hide the Transaction ID column (column H)
    sheet.batch_update({"requests": [{"updateDimensionProperties": {
        "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": 7, "endIndex": 8},
        "properties": {"hiddenByUser": True},
        "fields": "hiddenByUser"
    }}]})

    return rows


def rebuild_summary(sheet, transactions):
    try:
        ws = sheet.worksheet("Summary")
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet("Summary", rows=100, cols=4)

    cat_totals = {}
    card_totals = {}
    for row in transactions:
        cat = row[6] or "Uncategorized"
        amount = float(row[2])
        cat_totals[cat] = round(cat_totals.get(cat, 0) + amount, 2)
        card_totals[row[3]] = round(card_totals.get(row[3], 0) + amount, 2)

    output = [["By Category", "Total ($)"]]
    for cat, total in sorted(cat_totals.items(), key=lambda x: -x[1]):
        output.append([cat, total])

    output.append(["", ""])
    output.append(["By Card", "Total ($)"])
    for card, total in sorted(card_totals.items(), key=lambda x: -x[1]):
        output.append([card, total])

    ws.update(f"A1:B{len(output)}", output)
    ws.format("A1:B1", {"textFormat": {"bold": True}})
    ws.format(f"A{len(cat_totals) + 3}:B{len(cat_totals) + 3}", {"textFormat": {"bold": True}})
    ws.freeze(rows=1)


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Connecting to Google Sheets...")
    gc = gspread.oauth(credentials_filename=CREDENTIALS_FILE, authorized_user_filename=TOKEN_FILE)
    sheet = gc.open_by_key(SHEET_ID)

    print("Loading categorization rules...")
    rules = load_rules(sheet)
    print(f"  {len(rules)} rule(s) loaded.")

    print("Fetching transactions from Plaid...")
    plaid_client = make_plaid_client()
    all_transactions = []
    for token, name in zip(ACCESS_TOKENS, CARD_NAMES):
        print(f"  Fetching {name}...")
        txns = fetch_transactions(plaid_client, token, name)
        print(f"    {len(txns)} transactions.")
        all_transactions.extend(txns)

    print("Syncing Transactions tab...")
    rows = sync_transactions(sheet, all_transactions, rules)

    print("Rebuilding Summary tab...")
    rebuild_summary(sheet, rows)

    print(f"\nDone! {len(rows)} transactions synced.")
    print(f"Open your sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}")
