"""무료 리포트 발급 경로 rate limit — 같은 IP에서 분당 3회 초과 시 429"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app

_BODY = {"analyze_request": {
    "user_profile": {"age": 30, "monthly_income": 400, "investment_goal": "자산증식",
                     "investment_period": 5, "risk_tolerance": "중립형"},
    "portfolio": {"total_asset": 1000, "monthly_saving": 50,
                  "allocations": [{"asset_name": "A", "asset_type": "해외주식", "weight": 100}]},
}}


def test_payment_request_limited_after_three_per_minute():
    client = TestClient(app)
    with patch("routers.payment.storage_set"):
        codes = [client.post("/payment/request", json=_BODY).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_report_generate_limited_after_three_per_minute():
    client = TestClient(app)
    with patch("routers.report.get_confirmed_payment", return_value=None):
        codes = [client.post("/report/generate", json={"report_token": "rpt_x"}).status_code for _ in range(4)]
    assert codes == [403, 403, 403, 429]
