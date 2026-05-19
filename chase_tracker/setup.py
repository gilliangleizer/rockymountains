"""
One-time setup: link two Chase accounts via Plaid and authorize Google Sheets.
Run: python chase_tracker/setup.py
"""
import os
import threading
import webbrowser
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv, set_key
import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
import gspread

DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(DIR, ".env")
CREDENTIALS_FILE = os.path.join(DIR, "credentials.json")
TOKEN_FILE = os.path.join(DIR, "token.json")

load_dotenv(ENV_FILE)

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENV", "development")

LINK_HTML = """
<!DOCTYPE html><html><head><title>Chase Tracker Setup</title>
<style>
  body{font-family:sans-serif;max-width:480px;margin:80px auto;text-align:center;color:#222}
  h2{margin-bottom:8px} p{color:#555}
  button{padding:12px 28px;font-size:16px;cursor:pointer;background:#0070f3;color:white;
         border:none;border-radius:8px;margin-top:16px}
  button:hover{background:#0060d4}
  #status{margin-top:24px;font-size:14px;color:#333;min-height:20px}
  .done{color:green;font-weight:bold}
</style></head>
<body>
  <h2>Chase Tracker Setup</h2>
  {% if done %}
    <p class="done">Both cards connected! You can close this tab.</p>
    <p>Return to the terminal to complete Google Sheets setup.</p>
  {% else %}
    <p>Step {{ card_num }} of 2: click below to connect <strong>Chase Card {{ card_num }}</strong>.</p>
    <button id="btn">Connect Card {{ card_num }}</button>
    <p id="status"></p>
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    <script>
      const handler = Plaid.create({
        token: "{{ link_token }}",
        onSuccess: function(public_token) {
          document.getElementById('status').textContent = 'Saving token...';
          document.getElementById('btn').disabled = true;
          fetch('/exchange', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({public_token})
          }).then(r => r.json()).then(d => {
            document.getElementById('status').textContent = d.message;
            if (d.reload) setTimeout(() => location.reload(), 1500);
          });
        },
        onExit: function(err) {
          if (err) document.getElementById('status').textContent = 'Error: ' + err.display_message;
        }
      });
      document.getElementById('btn').onclick = () => handler.open();
    </script>
  {% endif %}
</body></html>
"""

app = Flask(__name__)
state = {"card": 1, "done": False}
shutdown_event = threading.Event()


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


plaid_client = None  # initialized after env check


@app.route("/")
def index():
    if state["done"]:
        return render_template_string(LINK_HTML, done=True, card_num=0, link_token="")

    req = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="Chase Tracker",
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id="chase-tracker"),
    )
    link_token = plaid_client.link_token_create(req)["link_token"]
    return render_template_string(LINK_HTML, done=False, link_token=link_token, card_num=state["card"])


@app.route("/exchange", methods=["POST"])
def exchange():
    public_token = request.json["public_token"]
    resp = plaid_client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    )
    access_token = resp["access_token"]
    set_key(ENV_FILE, f"PLAID_ACCESS_TOKEN_{state['card']}", access_token)
    print(f"  Card {state['card']} token saved.")

    if state["card"] < 2:
        state["card"] = 2
        return jsonify({"message": "Card 1 connected! Loading card 2...", "reload": True})
    else:
        state["done"] = True
        shutdown_event.set()
        return jsonify({"message": "Both cards connected!", "reload": False})


def run_flask():
    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", 5050, app)
    shutdown_event.wait()
    server.shutdown()


if __name__ == "__main__":
    if not PLAID_CLIENT_ID or not PLAID_SECRET:
        print("Add your Plaid credentials to chase_tracker/.env first:")
        print("  PLAID_CLIENT_ID=...")
        print("  PLAID_SECRET=...")
        print("\nSign up free at https://dashboard.plaid.com/signup")
        exit(1)

    plaid_client = make_plaid_client()

    print("Starting Plaid Link flow at http://localhost:5050 ...")
    server_thread = threading.Thread(target=run_flask, daemon=True)
    server_thread.start()
    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:5050")).start()

    shutdown_event.wait()
    print("Plaid setup complete.\n")

    # Google Sheets OAuth
    if not os.path.exists(CREDENTIALS_FILE):
        print("Google Sheets credentials not found.")
        print("To get them:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create a project > APIs & Services > Enable 'Google Sheets API'")
        print("  3. Credentials > Create > OAuth 2.0 Client ID > Desktop app > Download JSON")
        print(f"  4. Save the file as: {CREDENTIALS_FILE}")
        input("\nPress Enter when credentials.json is in place...")

    print("Opening browser for Google Sheets authorization...")
    gc = gspread.oauth(
        credentials_filename=CREDENTIALS_FILE,
        authorized_user_filename=TOKEN_FILE,
    )
    print("Google Sheets authorized.\n")
    print("Setup complete!")
    print("Next steps:")
    print("  1. Copy chase_tracker/.env.example to chase_tracker/.env (if not done)")
    print("  2. Set GOOGLE_SHEET_ID in chase_tracker/.env")
    print("  3. Run: python chase_tracker/sync.py")
