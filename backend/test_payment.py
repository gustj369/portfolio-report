import asyncio
import sys
import types
import unittest


try:
    from fastapi import HTTPException
except Exception:
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    class APIRouter:
        def __init__(self, *args, **kwargs):
            pass

        def post(self, *args, **kwargs):
            return lambda fn: fn

        def get(self, *args, **kwargs):
            return lambda fn: fn

    fastapi_module = types.ModuleType("fastapi")
    fastapi_module.APIRouter = APIRouter
    fastapi_module.HTTPException = HTTPException
    fastapi_module.Depends = lambda dependency: dependency
    sys.modules.setdefault("fastapi", fastapi_module)


try:
    from config import Settings
except Exception:
    class Settings:
        def __init__(
            self,
            report_price_krw: int = 4900,
            toss_secret_key: str = "",
            toss_client_key: str = "test_client_key",
            admin_alert_webhook_url: str = "",
            redis_url: str = "",
        ):
            self.report_price_krw = report_price_krw
            self.toss_secret_key = toss_secret_key
            self.toss_client_key = toss_client_key
            self.admin_alert_webhook_url = admin_alert_webhook_url
            self.redis_url = redis_url

    config_module = types.ModuleType("config")
    config_module.Settings = Settings
    config_module.get_settings = lambda: Settings()
    sys.modules.setdefault("config", config_module)


try:
    import httpx  # noqa: F401
except Exception:
    httpx_module = types.ModuleType("httpx")
    httpx_module.RequestError = RuntimeError
    sys.modules.setdefault("httpx", httpx_module)

from routers import payment


class FakeAnalyzeRequest:
    def model_dump(self, mode: str = "json"):
        return {"portfolio": "sample"}


class FakeRequestBody:
    analyze_request = FakeAnalyzeRequest()


class PaymentRouterTest(unittest.TestCase):
    def setUp(self):
        self.original_storage_get = payment.storage_get
        self.original_storage_set = payment.storage_set
        self.original_storage_delete = payment.storage_delete

    def tearDown(self):
        payment.storage_get = self.original_storage_get
        payment.storage_set = self.original_storage_set
        payment.storage_delete = self.original_storage_delete

    def test_paid_request_without_secret_key_is_blocked_before_storage(self):
        storage_called = False

        def fake_storage_set(*args, **kwargs):
            nonlocal storage_called
            storage_called = True

        payment.storage_set = fake_storage_set

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(payment.request_payment(FakeRequestBody(), Settings(report_price_krw=4900, toss_secret_key="")))

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("결제 서버 설정", ctx.exception.detail)
        self.assertFalse(storage_called)

    def test_confirm_storage_failure_returns_friendly_503(self):
        def fake_storage_get(key):
            if key.startswith(payment._PENDING_PFX):
                return {"amount": 0, "analyze_request": {"portfolio": "sample"}}
            return None

        payment.storage_get = fake_storage_get
        payment.storage_delete = lambda key: (_ for _ in ()).throw(RuntimeError("redis down"))

        body = payment.PaymentConfirmInput(payment_key="", order_id="order_test", amount=0)

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(payment.confirm_payment(body, Settings(report_price_krw=0)))

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("저장소 연결", ctx.exception.detail)

    def test_status_storage_failure_returns_friendly_503(self):
        payment.storage_get = lambda key: (_ for _ in ()).throw(RuntimeError("redis down"))

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(payment.get_payment_status("order_test"))

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("저장소 연결", ctx.exception.detail)

    def test_post_approval_storage_failure_logs_manual_recovery_context(self):
        with self.assertLogs(payment.logger, level="CRITICAL") as logs:
            payment._log_post_approval_storage_failure(
                order_id="order_test",
                amount=4900,
                payment_key="payment_key_secret",
                error=RuntimeError("redis down"),
            )

        message = "\n".join(logs.output)
        self.assertIn("수동 복구 필요", message)
        self.assertIn("order_test", message)
        self.assertIn("payment_", message)
        self.assertNotIn("payment_key_secret", message)

    def test_post_approval_storage_failure_sends_admin_alert(self):
        calls = []
        original_send_admin_alert = payment.send_admin_alert
        payment.send_admin_alert = lambda **kwargs: calls.append(kwargs) or True
        try:
            payment._log_post_approval_storage_failure(
                order_id="order_test",
                amount=4900,
                payment_key="payment_key_secret",
                error=RuntimeError("redis down"),
                alert_webhook_url="https://example.com/webhook",
            )
        finally:
            payment.send_admin_alert = original_send_admin_alert

        self.assertEqual(calls[0]["title"], "결제 승인 후 저장 실패")
        self.assertEqual(calls[0]["webhook_url"], "https://example.com/webhook")
        self.assertIn("order_test", calls[0]["message"])
        self.assertNotIn("payment_key_secret", calls[0]["message"])


if __name__ == "__main__":
    unittest.main()
