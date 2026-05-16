import json
import unittest

from services.alert_service import _build_slack_payload


class AlertServiceTest(unittest.TestCase):
    def test_slack_payload_includes_text_fallback_and_blocks(self):
        payload = _build_slack_payload("결제 승인 후 저장 실패", "order_id=order_test")

        self.assertIn("text", payload)
        self.assertEqual(payload["blocks"][0]["type"], "header")
        self.assertEqual(payload["blocks"][1]["type"], "section")
        self.assertIn("order_test", payload["blocks"][1]["text"]["text"])

        json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
