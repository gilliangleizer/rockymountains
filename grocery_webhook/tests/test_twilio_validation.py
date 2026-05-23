import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-twilio-token")
os.environ.setdefault("NOTION_TOKEN", "test-notion-token")
os.environ.setdefault("ALLOWED_NUMBERS", "+13038757999")

sys.modules["anthropic"] = SimpleNamespace(Anthropic=Mock(return_value=Mock()))
sys.modules["skills.calendar.tools"] = SimpleNamespace(
    TOOLS=[],
    HANDLERS={},
    SYSTEM_PROMPT_SECTION="",
)

import app as webhook_app


class TwilioValidationTests(unittest.TestCase):
    def setUp(self):
        webhook_app.app.config.update(TESTING=True)
        webhook_app.conversations.clear()
        self.client = webhook_app.app.test_client()
        self.form = {
            "Body": "show list",
            "From": "whatsapp:+13038757999",
        }

    def test_missing_auth_token_rejects_request(self):
        with patch.dict(webhook_app.os.environ, {"TWILIO_AUTH_TOKEN": ""}):
            response = self.client.post("/webhook", data=self.form)

        self.assertEqual(response.status_code, 403)

    def test_invalid_signature_rejects_request_before_claude(self):
        validator = Mock()
        validator.validate.return_value = False

        with (
            patch.object(webhook_app, "RequestValidator", return_value=validator),
            patch.object(webhook_app.claude.messages, "create") as create,
        ):
            response = self.client.post(
                "/webhook",
                data=self.form,
                headers={"X-Twilio-Signature": "bad-signature"},
            )

        self.assertEqual(response.status_code, 403)
        create.assert_not_called()

    def test_valid_signature_reaches_webhook_logic(self):
        validator = Mock()
        validator.validate.return_value = True
        message = SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="Current list")],
        )

        with (
            patch.object(webhook_app, "RequestValidator", return_value=validator),
            patch.object(webhook_app.claude.messages, "create", return_value=message) as create,
        ):
            response = self.client.post(
                "/webhook",
                data=self.form,
                headers={"X-Twilio-Signature": "valid-signature"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Current list", response.data)
        create.assert_called_once()
        validator.validate.assert_called_once()

    def test_allowed_numbers_still_block_after_valid_signature(self):
        validator = Mock()
        validator.validate.return_value = True

        with (
            patch.object(webhook_app, "RequestValidator", return_value=validator),
            patch.object(webhook_app.claude.messages, "create") as create,
        ):
            response = self.client.post(
                "/webhook",
                data={"Body": "show list", "From": "whatsapp:+19999999999"},
                headers={"X-Twilio-Signature": "valid-signature"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.count(b"<Message>"), 0)
        create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
