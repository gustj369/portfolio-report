"""
결제 주문 복구 dry-run 스크립트.

현재 버전은 저장/리포트 재생성을 수행하지 않고, order_id 기준으로 복구에 필요한
스토리지 상태만 점검합니다.

실행 예:
    python scripts/recover_payment_order.py --order-id order_xxx --dry-run
"""
import argparse
import base64
import hmac
import json
import logging
import os
import sys
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from urllib import error, request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.storage import (
    storage_acquire_lock,
    storage_confirm_payment_recovery,
    storage_get,
    storage_release_lock,
)

logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s")

PENDING_PFX = "pay:pending:"
IDEMPOTENCY_PFX = "pay:idempotency:"
CONFIRMED_PFX = "pay:confirmed:"
RECOVERY_LOCK_PFX = "recovery:lock:"
REPORT_RECORD_PFX = "report:record:"
TOSS_ORDER_URL = "https://api.tosspayments.com/v1/payments/orders/{order_id}"
DEFAULT_REPORT_API_BASE_URL = "http://localhost:8000"
RECOVERY_LOCK_TTL_SECONDS = 300
KST = timezone(timedelta(hours=9))
_JSON_OUTPUT = False
_QUIET = False
_EVENTS: list[str] = []
_WEAK_RECOVERY_TOKENS = {"check-only", "changeme", "change-me", "test", "token", "admin"}


def _mask(value: str, visible: int = 8) -> str:
    if not value:
        return ""
    return f"{value[:visible]}..."


def _print_section(title: str) -> None:
    if _JSON_OUTPUT:
        _EVENTS.append(f"section:{title}")
        return
    if _QUIET:
        return
    print(f"\n== {title} ==")


def _emit(message: str) -> None:
    if _JSON_OUTPUT:
        _EVENTS.append(message)
        return
    if _QUIET:
        return
    print(message)


def _public_result(result: dict) -> dict:
    cleaned = deepcopy(result)
    cleaned["summary"] = _result_summary(cleaned)

    def scrub(value):
        if isinstance(value, dict):
            for key in list(value.keys()):
                if key.startswith("_"):
                    value.pop(key)
                else:
                    scrub(value[key])
        elif isinstance(value, list):
            for item in value:
                scrub(item)

    scrub(cleaned)
    return cleaned


def _result_summary(result: dict) -> dict:
    storage = result.get("storage") or {}
    toss = result.get("toss") or {}
    amount_check = toss.get("amount_check") or {}
    report_generation = result.get("report_generation") or {}
    lock = result.get("lock") or {}

    return {
        "order_id": result.get("order_id"),
        "mode": result.get("mode"),
        "decision": result.get("decision"),
        "pending": storage.get("pending"),
        "idempotency": storage.get("idempotency"),
        "confirmed": storage.get("confirmed"),
        "report_token": result.get("report_token") or storage.get("report_token"),
        "confirm_ready": result.get("confirm_ready"),
        "confirm_blockers": result.get("confirm_blockers"),
        "toss_checked": toss.get("checked"),
        "toss_found": toss.get("found"),
        "toss_status": toss.get("status"),
        "amount_check": amount_check.get("status"),
        "lock_acquired": lock.get("acquired"),
        "report_generation_requested": report_generation.get("requested"),
        "report_generation_skipped": report_generation.get("skipped"),
        "report_generation_reason": report_generation.get("reason"),
        "report_generation_status": report_generation.get("status"),
        "report_generation_guidance": report_generation.get("guidance"),
    }


def _get_toss_secret_key() -> str:
    env_secret = os.getenv("TOSS_SECRET_KEY")
    if env_secret:
        return env_secret
    try:
        from config import get_settings
        return get_settings().toss_secret_key
    except Exception:
        return ""


def _read_recovery_token_from_stdin() -> str:
    return sys.stdin.readline().strip()


def _validate_admin_recovery_token(confirm_write: bool, provided_token: str = "") -> tuple[bool, str]:
    configured_token = os.getenv("ADMIN_RECOVERY_TOKEN", "")
    if not configured_token:
        return False, "ADMIN_RECOVERY_TOKEN is required for recovery inspection."

    if not confirm_write:
        return True, ""

    if len(configured_token) < 32 or configured_token.lower() in _WEAK_RECOVERY_TOKENS:
        return False, "ADMIN_RECOVERY_TOKEN must be a strong value of at least 32 characters for --confirm."
    if not provided_token:
        return False, "--recovery-token-stdin or --recovery-token is required for write-enabled --confirm."
    if not hmac.compare_digest(configured_token, provided_token):
        return False, "--recovery-token does not match ADMIN_RECOVERY_TOKEN."
    return True, ""


def _lock_busy_result(order_id: str, mode: str, lock_key: str) -> dict:
    return {
        "order_id": order_id,
        "mode": mode,
        "lock": {
            "acquired": False,
            "key": lock_key,
            "ttl_seconds": RECOVERY_LOCK_TTL_SECONDS,
            "guidance": (
                "Another recovery run is handling this order_id. "
                "Wait up to the lock TTL, then re-run dry-run before retrying confirm."
            ),
        },
        "decision": "another recovery process holds the lock",
    }


def fetch_toss_payment_by_order_id(order_id: str, secret_key: str) -> dict | None:
    auth = base64.b64encode(f"{secret_key}:".encode("utf-8")).decode("utf-8")
    req = request.Request(
        TOSS_ORDER_URL.format(order_id=order_id),
        headers={"Authorization": f"Basic {auth}"},
        method="GET",
    )

    try:
        with request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        _emit(f"Toss lookup failed: http_status={e.code}, guidance={_toss_http_guidance(e.code)}, body={body}")
        return None


def _report_generate_http_guidance(status_code: int) -> str:
    if status_code == 403:
        return "confirmed payment data was not found; verify pay:confirmed:{report_token} and shared storage settings"
    if status_code == 404:
        return "report endpoint or record was not found; verify backend URL and report token"
    if status_code == 409:
        return "report is not ready or is already in progress; check /report/status/{report_token}"
    if status_code == 429:
        return "request was rate limited; wait before retrying"
    if 500 <= status_code < 600:
        return "backend report generation failed; inspect backend logs and retry after the service is healthy"
    return "unexpected report generation response; inspect response body and backend logs"


def _report_record_decision(existing_record: dict | None) -> dict:
    if not existing_record:
        return {"action": "request", "reason": "report record missing"}

    status = existing_record.get("status")
    if status in ("ready", "pending", "generating"):
        return {
            "action": "skip",
            "reason": f"report already {status}",
            "status": status,
            "download_url": existing_record.get("download_url"),
        }
    if status == "error":
        return {
            "action": "request",
            "reason": "report record is error",
            "status": status,
            "error_message": existing_record.get("error_message"),
        }
    return {
        "action": "request",
        "reason": f"unknown report status: {status}",
        "status": status,
    }


def request_report_generation(report_token: str, api_base_url: str = DEFAULT_REPORT_API_BASE_URL) -> dict:
    existing_record = storage_get(f"{REPORT_RECORD_PFX}{report_token}")
    record_decision = _report_record_decision(existing_record)
    if record_decision["action"] == "skip":
        return {
            "requested": False,
            "skipped": True,
            **record_decision,
        }
    if record_decision.get("status") == "error":
        _emit(f"report record is error; requesting regeneration: {record_decision.get('error_message')}")

    url = f"{api_base_url.rstrip('/')}/report/generate"
    payload = json.dumps({"report_token": report_token}).encode("utf-8")
    req = request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8")
            return {
                "requested": True,
                "http_status": response.status,
                "response": json.loads(body) if body else None,
            }
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        return {
            "requested": False,
            "http_status": e.code,
            "error": body,
            "guidance": _report_generate_http_guidance(e.code),
        }
    except (error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return {
            "requested": False,
            "error": str(e),
            "guidance": "could not call /report/generate; verify backend URL, network, and JSON response",
        }
    except (error.URLError, TimeoutError, json.JSONDecodeError) as e:
        _emit(f"Toss lookup failed: {e}")
        return None


def _toss_http_guidance(status_code: int) -> str:
    if status_code == 400:
        return "bad request; check order_id format and request parameters"
    if status_code == 401:
        return "authentication failed; check TOSS_SECRET_KEY"
    if status_code == 403:
        return "permission denied; check Toss account/environment key"
    if status_code == 404:
        return "payment not found for this order_id"
    if status_code == 429:
        return "rate limited; retry after waiting"
    if 500 <= status_code < 600:
        return "Toss server error; retry later and check Toss status"
    return "unexpected Toss response; inspect response body"


def _compare_amounts(pending: dict | None, payment: dict) -> None:
    if not pending:
        return {"status": "skipped", "reason": "pending missing"}

    pending_amount = pending.get("amount")
    toss_amount = payment.get("totalAmount")
    if pending_amount is None or toss_amount is None:
        return {"status": "skipped", "pending_amount": pending_amount, "toss_amount": toss_amount}

    if int(pending_amount) == int(toss_amount):
        return {"status": "match", "pending_amount": int(pending_amount), "toss_amount": int(toss_amount)}
    return {"status": "mismatch", "pending_amount": int(pending_amount), "toss_amount": int(toss_amount)}


def fetch_toss_lookup(order_id: str, pending: dict | None = None) -> dict:
    _print_section("Toss payment lookup")
    secret_key = _get_toss_secret_key()
    if not secret_key:
        _emit("Toss lookup skipped: TOSS_SECRET_KEY is not configured")
        return {"checked": False, "skip_reason": "TOSS_SECRET_KEY is not configured"}

    payment = fetch_toss_payment_by_order_id(order_id, secret_key)
    if not payment:
        _emit("Toss payment: not found or lookup failed")
        return {"checked": True, "found": False}

    amount_check = _compare_amounts(pending, payment)
    _emit(f"payment_key_prefix: {_mask(payment.get('paymentKey', ''))}")
    _emit(f"status: {payment.get('status')}")
    _emit(f"total_amount: {payment.get('totalAmount')}")
    _emit(f"approved_at: {payment.get('approvedAt')}")
    if amount_check["status"] == "match":
        _emit(f"amount_check: match ({amount_check['pending_amount']})")
    elif amount_check["status"] == "mismatch":
        _emit(
            "amount_check: mismatch "
            f"(pending={amount_check['pending_amount']}, toss={amount_check['toss_amount']})"
        )
    elif amount_check.get("reason") == "pending missing":
        _emit("amount_check: skipped (pending missing)")
    else:
        _emit(
            "amount_check: skipped "
            f"(pending={amount_check.get('pending_amount')}, toss={amount_check.get('toss_amount')})"
        )
    return {
        "checked": True,
        "found": True,
        "payment_key_prefix": _mask(payment.get("paymentKey", "")),
        "_payment_key": payment.get("paymentKey", ""),
        "status": payment.get("status"),
        "total_amount": payment.get("totalAmount"),
        "approved_at": payment.get("approvedAt"),
        "amount_check": amount_check,
    }


def print_toss_lookup(order_id: str, pending: dict | None = None) -> None:
    fetch_toss_lookup(order_id, pending)


def build_inspection(order_id: str, check_toss: bool = False) -> dict:
    _EVENTS.clear()
    _print_section("Recovery dry-run")
    _emit(f"order_id: {order_id}")
    _emit("mode: dry-run only")

    pending = storage_get(f"{PENDING_PFX}{order_id}")
    idempotency = storage_get(f"{IDEMPOTENCY_PFX}{order_id}")

    _print_section("Storage status")
    _emit(f"pending: {'found' if pending else 'missing'}")
    _emit(f"idempotency: {'found' if idempotency else 'missing'}")

    result = {
        "order_id": order_id,
        "mode": "dry-run only",
        "storage": {
            "pending": bool(pending),
            "idempotency": bool(idempotency),
        },
        "toss": None,
        "decision": "",
        "events": _EVENTS,
        "_pending": pending,
    }

    if check_toss:
        result["toss"] = fetch_toss_lookup(order_id, pending)

    if idempotency and idempotency.get("report_token"):
        report_token = idempotency["report_token"]
        confirmed = storage_get(f"{CONFIRMED_PFX}{report_token}")
        result["storage"]["report_token"] = report_token
        result["storage"]["confirmed"] = bool(confirmed)
        result["decision"] = "already processed; do not issue a duplicate report token"
        _emit(f"report_token: {report_token}")
        _emit(f"confirmed: {'found' if confirmed else 'missing'}")
        _emit(result["decision"])
        return result

    if pending:
        _print_section("Pending payment")
        analyze_request = pending.get("analyze_request")
        result["storage"]["pending_amount"] = pending.get("amount")
        result["storage"]["pending_created_at"] = pending.get("created_at")
        result["storage"]["analyze_request"] = bool(analyze_request)
        result["decision"] = "verify Toss approval manually, then run a confirmed recovery path when implemented"
        _emit(f"amount: {pending.get('amount')}")
        _emit(f"created_at: {pending.get('created_at')}")
        _emit(f"analyze_request: {'found' if analyze_request else 'missing'}")
        _emit(result["decision"])
        return result

    _print_section("Manual action required")
    result["decision"] = "do not generate a report automatically"
    _emit("pending data is missing; restore analyze_request from request logs or customer input before recovery")
    _emit(f"decision: {result['decision']}")
    return result


def inspect_order(order_id: str, check_toss: bool = False, output_json: bool = False) -> int:
    global _JSON_OUTPUT
    _JSON_OUTPUT = output_json
    try:
        result = build_inspection(order_id, check_toss=check_toss)
        if output_json:
            print(json.dumps(_public_result(result), ensure_ascii=False, indent=2))
    finally:
        _JSON_OUTPUT = False
    return 0


def _confirm_readiness(result: dict) -> tuple[bool, list[str]]:
    reasons = []
    storage = result.get("storage") or {}
    toss = result.get("toss") or {}
    amount_check = toss.get("amount_check") or {}

    if not storage.get("pending"):
        reasons.append("pending missing")
    if storage.get("idempotency") or storage.get("confirmed"):
        reasons.append("already processed")
    if not storage.get("analyze_request"):
        reasons.append("analyze_request missing")
    if not toss.get("checked"):
        reasons.append("Toss lookup required")
    elif not toss.get("found"):
        reasons.append("Toss payment not found")
    elif toss.get("status") != "DONE":
        reasons.append(f"Toss status is {toss.get('status')}")
    if amount_check.get("status") != "match":
        reasons.append(f"amount_check is {amount_check.get('status')}")

    return not reasons, reasons


def preview_confirm(order_id: str, output_json: bool = False) -> int:
    global _JSON_OUTPUT
    _JSON_OUTPUT = output_json
    lock_key = f"{RECOVERY_LOCK_PFX}{order_id}"
    owner = f"recover-payment:{os.getpid()}"
    lock_acquired = False
    try:
        if not storage_acquire_lock(lock_key, owner, ttl=RECOVERY_LOCK_TTL_SECONDS):
            result = _lock_busy_result(order_id, "confirm preview", lock_key)
            print(json.dumps(result, ensure_ascii=False, indent=2) if output_json else result["decision"])
            return 2
        lock_acquired = True

        result = build_inspection(order_id, check_toss=True)
        ready, reasons = _confirm_readiness(result)
        result["mode"] = "confirm preview"
        result["lock"] = {"acquired": True, "key": lock_key}
        result["confirm_ready"] = ready
        result["confirm_blockers"] = reasons
        result["decision"] = (
            "confirm write path is not implemented; no recovery data was written"
            if ready
            else "confirm blocked; no recovery data was written"
        )
        if output_json:
            print(json.dumps(_public_result(result), ensure_ascii=False, indent=2))
        else:
            _print_section("Confirm preview")
            _emit(f"confirm_ready: {ready}")
            _emit(f"confirm_blockers: {', '.join(reasons) if reasons else 'none'}")
            _emit(result["decision"])
        return 0 if ready else 2
    finally:
        try:
            if lock_acquired:
                storage_release_lock(lock_key, owner)
        finally:
            _JSON_OUTPUT = False


def confirm_order(
    order_id: str,
    output_json: bool = False,
    generate_report: bool = False,
    report_api_url: str = DEFAULT_REPORT_API_BASE_URL,
) -> int:
    global _JSON_OUTPUT
    _JSON_OUTPUT = output_json
    lock_key = f"{RECOVERY_LOCK_PFX}{order_id}"
    owner = f"recover-payment:{os.getpid()}"
    lock_acquired = False
    try:
        if not storage_acquire_lock(lock_key, owner, ttl=RECOVERY_LOCK_TTL_SECONDS):
            result = _lock_busy_result(order_id, "confirm", lock_key)
            print(json.dumps(result, ensure_ascii=False, indent=2) if output_json else result["decision"])
            return 2
        lock_acquired = True

        result = build_inspection(order_id, check_toss=True)
        ready, reasons = _confirm_readiness(result)
        result["mode"] = "confirm"
        result["lock"] = {"acquired": True, "key": lock_key}
        result["confirm_ready"] = ready
        result["confirm_blockers"] = reasons

        if not ready:
            result["decision"] = "confirm blocked; no recovery data was written"
            if output_json:
                print(json.dumps(_public_result(result), ensure_ascii=False, indent=2))
            else:
                _print_section("Confirm blocked")
                _emit(f"confirm_blockers: {', '.join(reasons)}")
                _emit(result["decision"])
            return 2

        pending = result.get("_pending") or storage_get(f"{PENDING_PFX}{order_id}")
        if not pending:
            result["decision"] = "confirm blocked; pending disappeared before write"
            result["confirm_ready"] = False
            result["confirm_blockers"] = ["pending missing before write"]
            if output_json:
                print(json.dumps(_public_result(result), ensure_ascii=False, indent=2))
            else:
                _emit(result["decision"])
            return 2

        report_token = f"rpt_{uuid.uuid4().hex}"
        toss = result.get("toss") or {}
        confirmed_record = {
            "order_id": order_id,
            "payment_key": toss.get("_payment_key", ""),
            "amount": pending["amount"],
            "analyze_request": pending["analyze_request"],
            "confirmed_at": datetime.now(KST).isoformat(),
            "recovered_at": datetime.now(KST).isoformat(),
            "recovered_by": "scripts/recover_payment_order.py",
        }
        write_result = storage_confirm_payment_recovery(
            order_id=order_id,
            report_token=report_token,
            confirmed_record=confirmed_record,
            idempotency_record={"report_token": report_token},
            ttl=86400 * 7,
        )
        result["write"] = write_result
        if write_result.get("ok"):
            result["report_token"] = report_token
            result["decision"] = "confirm recovery written; idempotency saved, confirmed saved, pending deleted"
            if generate_report:
                result["report_generation"] = request_report_generation(report_token, report_api_url)
                if result["report_generation"].get("skipped"):
                    result["decision"] = f"confirm recovery written; report generation skipped: {result['report_generation'].get('reason')}"
                    exit_code = 0
                elif not result["report_generation"].get("requested"):
                    result["decision"] = "confirm recovery written, but report generation request failed"
                    exit_code = 1
                else:
                    result["decision"] = "confirm recovery written and report generation requested"
                    exit_code = 0
            else:
                result["report_generation"] = {"requested": False, "reason": "--generate-report not set"}
                exit_code = 0
        else:
            result["decision"] = f"confirm write blocked: {write_result.get('reason')}"
            exit_code = 2

        if output_json:
            print(json.dumps(_public_result(result), ensure_ascii=False, indent=2))
        else:
            _print_section("Confirm result")
            _emit(f"report_token: {result.get('report_token', '')}")
            _emit(result["decision"])
        return exit_code
    finally:
        try:
            if lock_acquired:
                storage_release_lock(lock_key, owner)
        finally:
            _JSON_OUTPUT = False


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or recover a payment order.")
    parser.add_argument("--order-id", required=True, help="Payment order_id, for example order_xxx")
    parser.add_argument("--dry-run", action="store_true", help="Inspect only. With --confirm, previews write readiness.")
    parser.add_argument("--confirm", action="store_true", help="Write confirmed recovery data when used without --dry-run.")
    parser.add_argument("--check-toss", action="store_true", help="Read Toss payment status by order_id.")
    parser.add_argument("--json", action="store_true", help="Print dry-run result as JSON.")
    parser.add_argument("--quiet", action="store_true", help="Suppress human-readable progress output.")
    parser.add_argument("--recovery-token", default="", help="Deprecated. Prefer --recovery-token-stdin to avoid shell history exposure.")
    parser.add_argument("--recovery-token-stdin", action="store_true", help="Read recovery token from stdin for write-enabled --confirm.")
    parser.add_argument("--generate-report", action="store_true", help="After a successful --confirm write, request /report/generate.")
    parser.add_argument("--report-api-url", default=DEFAULT_REPORT_API_BASE_URL, help="Backend base URL for --generate-report.")
    args = parser.parse_args()

    global _QUIET
    _QUIET = args.quiet

    provided_recovery_token = args.recovery_token
    if args.recovery_token_stdin:
        provided_recovery_token = _read_recovery_token_from_stdin()

    token_ok, token_error = _validate_admin_recovery_token(
        confirm_write=args.confirm and not args.dry_run,
        provided_token=provided_recovery_token,
    )
    if not token_ok:
        print(token_error, file=sys.stderr)
        return 2

    try:
        if args.confirm:
            if args.dry_run:
                return preview_confirm(args.order_id, output_json=args.json)
            return confirm_order(
                args.order_id,
                output_json=args.json,
                generate_report=args.generate_report,
                report_api_url=args.report_api_url,
            )

        if not args.dry_run:
            print("--dry-run is required.", file=sys.stderr)
            return 2

        return inspect_order(args.order_id, check_toss=args.check_toss, output_json=args.json)
    except RuntimeError as e:
        print(f"storage error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
