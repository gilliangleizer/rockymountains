# Grocery Webhook Hardening Recommendations

## Summary

Review found three concrete risks in the grocery flow:

- Tool results are returned directly after the first Claude call, so Claude never sees tool outputs and cannot produce a final user-facing response when multiple tools or follow-up wording are needed: `grocery_webhook/app.py`.
- `clear_list` confirmation is prompt-only; the handler itself has no confirmation state, so an incorrect tool call can delete every grocery item: `grocery_webhook/skills/grocery/tools.py`, `grocery_webhook/skills/grocery/notion.py`.
- Notion delete calls in `clear_list` ignore failures but still count items as deleted, creating false success messages: `grocery_webhook/skills/grocery/notion.py`.

## Key Changes

- Add an explicit per-sender pending confirmation state for destructive grocery actions.
- Require exact `YES` from the same conversation before calling `clear_list`; otherwise return the confirmation prompt without mutating Notion.
- Update `clear_list` to count only successful deletes and report failures clearly.
- Improve webhook tool handling so tool failures are recorded consistently and the assistant can handle multiple tool calls predictably.
- Add `ALLOWED_NUMBERS` to `.env.example`, since the app already supports it but the sample env omits it.

## Public Interfaces

- No external API route changes.
- No Notion page schema changes.
- User-facing behavior change: "clear/remove all" becomes a real two-step confirmation guarded by app state, not just model instructions.

## Test Plan

- Unit-test grocery Notion helpers with mocked `requests`:
  - add item to a known heading.
  - duplicate item is not added.
  - remove item searches all stores or respects a provided store.
  - clear list reports partial delete failures.
- Unit-test webhook confirmation behavior with Flask test client and mocked Claude/tool calls:
  - clear request asks for confirmation and does not call Notion.
  - unrelated follow-up cancels or leaves confirmation according to chosen implementation.
  - exact `YES` from the same sender performs the clear.
  - `YES` from another sender does not clear.
- Run `python -m compileall grocery_webhook` and the new test suite.

## Assumptions

- Confirmation state can be in memory like current conversation history; persistence across process restarts is out of scope for this pass.
- Exact `YES` is the required destructive confirmation phrase.
- The existing WhatsApp webhook route and Claude model choice remain unchanged.

## Twilio Webhook Verification Note

Implemented Twilio webhook request verification on branch `twilio-webhook-verification`. Twilio recommends validating incoming webhook requests with the `X-Twilio-Signature` header, the exact webhook URL, all request parameters, and the account Auth Token, preferably via the official SDK `RequestValidator` rather than a custom implementation.

Sources:

- https://www.twilio.com/docs/usage/webhooks/webhooks-security
- https://www.twilio.com/docs/usage/tutorials/how-to-secure-your-flask-app-by-validating-incoming-twilio-requests
- https://www.twilio.com/docs/usage/webhooks/getting-started-twilio-webhooks
