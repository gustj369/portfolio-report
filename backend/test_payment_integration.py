import unittest


try:
    import fastapi as fastapi_module
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    HAS_TESTCLIENT = hasattr(fastapi_module, "FastAPI")
    TESTCLIENT_SKIP_REASON = ""
except Exception as exc:  # pragma: no cover - dependency-gated test
    FastAPI = None
    TestClient = None
    HAS_TESTCLIENT = False
    TESTCLIENT_SKIP_REASON = f"FastAPI TestClient unavailable: {exc}"


def _sample_analyze_request() -> dict:
    return {
        "analyze_request": {
            "user_profile": {
                "age": 35,
                "monthly_income": 400,
                "investment_goal": "자산증식",
                "investment_period": 5,
                "risk_tolerance": "중립형",
                "name": "테스트",
                "email": "",
            },
            "portfolio": {
                "total_asset": 1000,
                "monthly_saving": 50,
                "allocations": [
                    {
                        "asset_name": "현금",
                        "asset_type": "현금",
                        "weight": 100,
                    }
                ],
            },
        }
    }


class PaymentTestClientIntegrationTest(unittest.TestCase):
    def setUp(self):
        if not HAS_TESTCLIENT:
            self.skipTest(TESTCLIENT_SKIP_REASON or "FastAPI TestClient unavailable")

        from config import Settings
        from routers import payment

        self.Settings = Settings
        self.payment = payment
        self.app = FastAPI()
        self.app.include_router(self.payment.router)
        self.client = TestClient(self.app)

        self.original_storage_get = self.payment.storage_get
        self.original_storage_set = self.payment.storage_set
        self.original_storage_delete = self.payment.storage_delete
        self.app.dependency_overrides[self.payment.get_settings] = lambda: self.Settings(
            report_price_krw=4900,
            toss_secret_key="",
            toss_client_key="test_client_key",
        )

    def tearDown(self):
        if not HAS_TESTCLIENT:
            return
        self.payment.storage_get = self.original_storage_get
        self.payment.storage_set = self.original_storage_set
        self.payment.storage_delete = self.original_storage_delete
        self.app.dependency_overrides.clear()

    def test_paid_request_without_secret_key_returns_503(self):
        storage_called = False

        def fake_storage_set(*args, **kwargs):
            nonlocal storage_called
            storage_called = True

        self.payment.storage_set = fake_storage_set

        response = self.client.post("/payment/request", json=_sample_analyze_request())

        self.assertEqual(response.status_code, 503)
        self.assertIn("결제 서버 설정", response.json()["detail"])
        self.assertFalse(storage_called)

    def test_status_storage_failure_returns_503(self):
        self.payment.storage_get = lambda key: (_ for _ in ()).throw(RuntimeError("redis down"))

        response = self.client.get("/payment/status/order_test")

        self.assertEqual(response.status_code, 503)
        self.assertIn("저장소 연결", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
