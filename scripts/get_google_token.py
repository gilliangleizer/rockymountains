"""
One-time script to get a Google OAuth refresh token for the webhook.

Steps:
1. Go to https://console.cloud.google.com
2. Create a project → Enable the Google Calendar API
3. Go to APIs & Services → Credentials → Create OAuth client ID
   - Application type: Desktop app
   - Download the JSON → save as client_secret.json in the repo root
4. Run: python scripts/get_google_token.py
5. A browser window will open — sign in and allow access
6. Copy the three values printed below into Render environment variables

Note: client_secret.json is gitignored — never commit it.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n=== Add these to Render → Environment Variables ===")
    print(f"GOOGLE_CLIENT_ID={creds.client_id}")
    print(f"GOOGLE_CLIENT_SECRET={creds.client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
