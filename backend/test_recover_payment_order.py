import json
import unittest
from unittest.mock import patch
from urllib import error

from scripts import recover_payment_order


class RecoverPaymentOrderTest(unittest.TestCase):
    def test_toss_lookup_skips_without_secret_key(self):
        with patch("scripts.recover_payment_order._get_toss_secret_key", return_value=""):
            with patch("builtins.print") as mock_print:
                recover_payment_order.print_toss_lookup("order_test")

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("Toss lookup skipped", printed)

    def test_toss_lookup_prints_masked_payment_key(self):
        payment = {
            "paymentKey": "payment_key_secret",
            "status": "DONE",
            "totalAmount": 4900,
            "approvedAt": "2026-05-09T12:00:00+09:00",
        }
        with patch("scripts.recover_payment_order._get_toss_secret_key", return_value="secret"):
            with patch("scripts.recover_payment_order.fetch_toss_payment_by_order_id", return_value=payment):
                with patch("builtins.print") as mock_print:
                    recover_payment_order.print_toss_lookup("order_test")

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("payment_...", printed)
        self.assertIn("DONE", printed)
        self.assertNotIn("payment_key_secret", printed)

    def test_toss_lookup_compares_pending_amount(self):
        payment = {
            "paymentKey": "payment_key_secret",
            "status": "DONE",
            "totalAmount": 4900,
            "approvedAt": "2026-05-09T12:00:00+09:00",
        }
        pending = {"amount": 4900}
        with patch("scripts.recover_payment_order._get_toss_secret_key", return_value="secret"):
            with patch("scripts.recover_payment_order.fetch_toss_payment_by_order_id", return_value=payment):
                with patch("builtins.print") as mock_print:
                    recover_payment_order.print_toss_lookup("order_test", pending)

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("amount_check: match", printed)

    def test_toss_lookup_reports_amount_mismatch(self):
        payment = {
            "paymentKey": "payment_key_secret",
            "status": "DONE",
            "totalAmount": 9900,
            "approvedAt": "2026-05-09T12:00:00+09:00",
        }
        pending = {"amount": 4900}
        with patch("scripts.recover_payment_order._get_toss_secret_key", return_value="secret"):
            with patch("scripts.recover_payment_order.fetch_toss_payment_by_order_id", return_value=payment):
                with patch("builtins.print") as mock_print:
                    recover_payment_order.print_toss_lookup("order_test", pending)

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("amount_check: mismatch", printed)

    def test_toss_http_guidance_by_status(self):
        self.assertIn("TOSS_SECRET_KEY", recover_payment_order._toss_http_guidance(401))
        self.assertIn("not found", recover_payment_order._toss_http_guidance(404))
        self.assertIn("retry later", recover_payment_order._toss_http_guidance(500))

    def test_build_inspection_json_shape(self):
        def fake_storage_get(key):
            if key.startswith(recover_payment_order.PENDING_PFX):
                return {"amount": 4900, "created_at": "now", "analyze_request": {"ok": True}}
            return None

        with patch("scripts.recover_payment_order.storage_get", side_effect=fake_storage_get):
            with patch("builtins.print"):
                result = recover_payment_order.build_inspection("order_test", check_toss=False)

        self.assertEqual(result["order_id"], "order_test")
        self.assertTrue(result["storage"]["pending"])
        self.assertEqual(result["storage"]["pending_amount"], 4900)
        self.assertIn("verify Toss approval", result["decision"])

    def test_inspect_order_json_prints_valid_json(self):
        with patch("scripts.recover_payment_order.storage_get", return_value=None):
            with patch("builtins.print") as mock_print:
                recover_payment_order.inspect_order("order_test", output_json=True)

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn('"order_id": "order_test"', printed)
        self.assertIn('"summary"', printed)
        self.assertIn('"pending": false', printed)
        self.assertIn('"decision": "do not generate a report automatically"', printed)

    def test_public_result_builds_core_recovery_summary_fields(self):
        public = recover_payment_order._public_result({
            "order_id": "order_test",
            "confirm_ready": True,
            "report_generation": {
                "requested": False,
                "skipped": True,
                "reason": "report already pending",
            },
        })

        summary = public["summary"]
        self.assertTrue(summary["confirm_ready"])
        self.assertFalse(summary["report_generation_requested"])
        self.assertTrue(summary["report_generation_skipped"])
        self.assertEqual(summary["report_generation_reason"], "report already pending")

    def test_confirm_preview_uses_lock_and_does_not_write_recovery_data(self):
        calls = []

        def fake_storage_get(key):
            if key.startswith(recover_payment_order.PENDING_PFX):
                return {"amount": 4900, "created_at": "now", "analyze_request": {"ok": True}}
            return None

        payment = {
            "paymentKey": "payment_key_secret",
            "status": "DONE",
            "totalAmount": 4900,
            "approvedAt": "2026-05-09T12:00:00+09:00",
        }

        with patch("scripts.recover_payment_order.storage_get", side_effect=fake_storage_get):
            with patch("scripts.recover_payment_order.storage_acquire_lock", side_effect=lambda *args, **kwargs: calls.append(("acquire", args)) or True):
                with patch("scripts.recover_payment_order.storage_release_lock", side_effect=lambda *args, **kwargs: calls.append(("release", args)) or True):
                    with patch("scripts.recover_payment_order._get_toss_secret_key", return_value="secret"):
                        with patch("scripts.recover_payment_order.fetch_toss_payment_by_order_id", return_value=payment):
                            with patch("builtins.print"):
                                code = recover_payment_order.preview_confirm("order_test", output_json=True)

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "acquire")
        self.assertEqual(calls[-1][0], "release")

    def test_confirm_preview_blocks_when_lock_exists(self):
        with patch("scripts.recover_payment_order.storage_acquire_lock", return_value=False):
            with patch("scripts.recover_payment_order.storage_release_lock") as release_lock:
                with patch("builtins.print") as mock_print:
                    code = recover_payment_order.preview_confirm("order_test", output_json=True)

        self.assertEqual(code, 2)
        release_lock.assert_not_called()
        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        result = json.loads(printed)
        self.assertEqual(result["lock"]["ttl_seconds"], 300)
        self.assertIn("re-run dry-run", result["lock"]["guidance"])

    def test_confirm_order_writes_recovery_data_after_safety_checks(self):
        calls = []

        def fake_storage_get(key):
            if key.startswith(recover_payment_order.PENDING_PFX):
                return {"amount": 4900, "created_at": "now", "analyze_request": {"ok": True}}
            return None

        payment = {
            "paymentKey": "payment_key_secret",
            "status": "DONE",
            "totalAmount": 4900,
            "approvedAt": "2026-05-09T12:00:00+09:00",
        }

        def fake_confirm(**kwargs):
            calls.append(kwargs)
            return {"ok": True, "report_token": kwargs["report_token"]}

        with patch("scripts.recover_payment_order.storage_get", side_effect=fake_storage_get):
            with patch("scripts.recover_payment_order.storage_acquire_lock", return_value=True):
                with patch("scripts.recover_payment_order.storage_release_lock", return_value=True):
                    with patch("scripts.recover_payment_order.storage_confirm_payment_recovery", side_effect=fake_confirm):
                        with patch("scripts.recover_payment_order._get_toss_secret_key", return_value="secret"):
                            with patch("scripts.recover_payment_order.fetch_toss_payment_by_order_id", return_value=payment):
                                with patch("builtins.print") as mock_print:
                                    code = recover_payment_order.confirm_order("order_test", output_json=True)

        self.assertEqual(code, 0)
        self.assertEqual(calls[0]["order_id"], "order_test")
        self.assertEqual(calls[0]["confirmed_record"]["payment_key"], "payment_key_secret")
        self.assertEqual(calls[0]["idempotency_record"]["report_token"], calls[0]["report_token"])
        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn('"summary"', printed)
        self.assertIn('"confirm_ready": true', printed)
        self.assertNotIn("payment_key_secret", printed)

    def test_confirm_order_blocks_before_write_when_not_ready(self):
        with patch("scripts.recover_payment_order.storage_get", return_value=None):
            with patch("scripts.recover_payment_order.storage_acquire_lock", return_value=True):
                with patch("scripts.recover_payment_order.storage_release_lock", return_value=True):
                    with patch("scripts.recover_payment_order.storage_confirm_payment_recovery") as confirm_write:
                        with patch("builtins.print"):
                            code = recover_payment_order.confirm_order("order_test", output_json=True)

        self.assertEqual(code, 2)
        confirm_write.assert_not_called()

    def test_confirm_order_requests_report_generation_after_successful_write(self):
        def fake_storage_get(key):
            if key.startswith(recover_payment_order.PENDING_PFX):
                return {"amount": 4900, "created_at": "now", "analyze_request": {"ok": True}}
            return None

        payment = {
            "paymentKey": "payment_key_secret",
            "status": "DONE",
            "totalAmount": 4900,
            "approvedAt": "2026-05-09T12:00:00+09:00",
        }

        with patch("scripts.recover_payment_order.storage_get", side_effect=fake_storage_get):
            with patch("scripts.recover_payment_order.storage_acquire_lock", return_value=True):
                with patch("scripts.recover_payment_order.storage_release_lock", return_value=True):
                    with patch("scripts.recover_payment_order.storage_confirm_payment_recovery", return_value={"ok": True, "report_token": "rpt_test"}):
                        with patch("scripts.recover_payment_order._get_toss_secret_key", return_value="secret"):
                            with patch("scripts.recover_payment_order.fetch_toss_payment_by_order_id", return_value=payment):
                                with patch("scripts.recover_payment_order.request_report_generation", return_value={"requested": True, "http_status": 200}) as request_report:
                                    with patch("builtins.print"):
                                        code = recover_payment_order.confirm_order(
                                            "order_test",
                                            output_json=True,
                                            generate_report=True,
                                            report_api_url="http://backend.test",
                                        )

        self.assertEqual(code, 0)
        request_report.assert_called_once()

    def test_confirm_order_reports_report_generation_request_failure(self):
        def fake_storage_get(key):
            if key.startswith(recover_payment_order.PENDING_PFX):
                return {"amount": 4900, "created_at": "now", "analyze_request": {"ok": True}}
            return None

        payment = {
            "paymentKey": "payment_key_secret",
            "status": "DONE",
            "totalAmount": 4900,
            "approvedAt": "2026-05-09T12:00:00+09:00",
        }

        with patch("scripts.recover_payment_order.storage_get", side_effect=fake_storage_get):
            with patch("scripts.recover_payment_order.storage_acquire_lock", return_value=True):
                with patch("scripts.recover_payment_order.storage_release_lock", return_value=True):
                    with patch("scripts.recover_payment_order.storage_confirm_payment_recovery", return_value={"ok": True, "report_token": "rpt_test"}):
                        with patch("scripts.recover_payment_order._get_toss_secret_key", return_value="secret"):
                            with patch("scripts.recover_payment_order.fetch_toss_payment_by_order_id", return_value=payment):
                                with patch("scripts.recover_payment_order.request_report_generation", return_value={"requested": False, "error": "down"}):
                                    with patch("builtins.print"):
                                        code = recover_payment_order.confirm_order(
                                            "order_test",
                                            output_json=True,
                                            generate_report=True,
                                        )

        self.assertEqual(code, 1)

    def test_request_report_generation_skips_existing_ready_record(self):
        record = {
            "status": "ready",
            "download_url": "/report/download/rpt_test",
        }
        with patch("scripts.recover_payment_order.storage_get", return_value=record):
            with patch("scripts.recover_payment_order.request.urlopen") as urlopen:
                result = recover_payment_order.request_report_generation("rpt_test")

        self.assertFalse(result["requested"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["reason"], "report already ready")
        public = recover_payment_order._public_result({"report_generation": result})
        self.assertTrue(public["summary"]["report_generation_skipped"])
        self.assertEqual(public["summary"]["report_generation_reason"], "report already ready")
        urlopen.assert_not_called()

    def test_request_report_generation_skips_existing_pending_record(self):
        record = {"status": "pending"}
        with patch("scripts.recover_payment_order.storage_get", return_value=record):
            with patch("scripts.recover_payment_order.request.urlopen") as urlopen:
                result = recover_payment_order.request_report_generation("rpt_test")

        self.assertFalse(result["requested"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["reason"], "report already pending")
        public = recover_payment_order._public_result({"report_generation": result})
        self.assertTrue(public["summary"]["report_generation_skipped"])
        self.assertEqual(public["summary"]["report_generation_reason"], "report already pending")
        urlopen.assert_not_called()

    def test_request_report_generation_skips_existing_generating_record(self):
        record = {"status": "generating"}
        with patch("scripts.recover_payment_order.storage_get", return_value=record):
            with patch("scripts.recover_payment_order.request.urlopen") as urlopen:
                result = recover_payment_order.request_report_generation("rpt_test")

        self.assertFalse(result["requested"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["status"], "generating")
        self.assertEqual(result["reason"], "report already generating")
        public = recover_payment_order._public_result({"report_generation": result})
        self.assertTrue(public["summary"]["report_generation_skipped"])
        self.assertEqual(public["summary"]["report_generation_reason"], "report already generating")
        urlopen.assert_not_called()

    def test_report_record_decision_skips_in_progress_status(self):
        for status in ("pending", "generating"):
            decision = recover_payment_order._report_record_decision({"status": status})

            self.assertEqual(decision["action"], "skip")
            self.assertEqual(decision["status"], status)

    def test_report_generate_http_guidance_by_status(self):
        self.assertIn("confirmed payment", recover_payment_order._report_generate_http_guidance(403))
        self.assertIn("backend URL", recover_payment_order._report_generate_http_guidance(404))
        self.assertIn("status", recover_payment_order._report_generate_http_guidance(409))
        self.assertIn("backend report generation failed", recover_payment_order._report_generate_http_guidance(500))

    def test_request_report_generation_includes_http_guidance(self):
        http_error = error.HTTPError(
            url="http://backend.test/report/generate",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=None,
        )
        http_error.read = lambda: b"forbidden"

        with patch("scripts.recover_payment_order.storage_get", return_value=None):
            with patch("scripts.recover_payment_order.request.urlopen", side_effect=http_error):
                result = recover_payment_order.request_report_generation("rpt_test", "http://backend.test")

        self.assertFalse(result["requested"])
        self.assertEqual(result["http_status"], 403)
        self.assertIn("confirmed payment", result["guidance"])

    def test_request_report_generation_allows_error_record_regeneration(self):
        record = {
            "status": "error",
            "error_message": "failed",
        }

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"status":"pending"}'

        with patch("scripts.recover_payment_order.storage_get", return_value=record):
            with patch("scripts.recover_payment_order.request.urlopen", return_value=FakeResponse()) as urlopen:
                with patch("builtins.print"):
                    result = recover_payment_order.request_report_generation("rpt_test")

        self.assertTrue(result["requested"])
        self.assertEqual(result["http_status"], 200)
        urlopen.assert_called_once()

    def test_admin_recovery_token_allows_dry_run_with_existing_token(self):
        with patch.dict("os.environ", {"ADMIN_RECOVERY_TOKEN": "check-only"}):
            ok, message = recover_payment_order._validate_admin_recovery_token(confirm_write=False)

        self.assertTrue(ok)
        self.assertEqual(message, "")

    def test_admin_recovery_token_requires_strong_matching_token_for_write(self):
        strong_token = "a" * 32
        with patch.dict("os.environ", {"ADMIN_RECOVERY_TOKEN": strong_token}):
            ok, message = recover_payment_order._validate_admin_recovery_token(
                confirm_write=True,
                provided_token=strong_token,
            )

        self.assertTrue(ok)
        self.assertEqual(message, "")

    def test_admin_recovery_token_rejects_weak_write_token(self):
        with patch.dict("os.environ", {"ADMIN_RECOVERY_TOKEN": "check-only"}):
            ok, message = recover_payment_order._validate_admin_recovery_token(
                confirm_write=True,
                provided_token="check-only",
            )

        self.assertFalse(ok)
        self.assertIn("strong value", message)

    def test_read_recovery_token_from_stdin_strips_newline(self):
        with patch("sys.stdin") as stdin:
            stdin.readline.return_value = "secret-token\n"

            token = recover_payment_order._read_recovery_token_from_stdin()

        self.assertEqual(token, "secret-token")


if __name__ == "__main__":
    unittest.main()
