# Payment Recovery Guide

This guide is for operator-led recovery when Toss payment approval succeeds but report token issuance or report generation needs manual follow-up.

## Safety Rules

- Use this only after checking the real payment in Toss by `order_id`.
- Do not paste secret keys, full payment keys, customer input, or personal data into logs.
- For write recovery, set a strong `ADMIN_RECOVERY_TOKEN` of at least 32 characters.
- Prefer `--recovery-token-stdin` over `--recovery-token` so the token is not exposed in shell history.
- The script and backend must point to the same Redis/storage when using `--generate-report`.
- Do not run automatic recovery when pending data is missing and `analyze_request` cannot be restored first.

## Command Flow

Inspect only:

```bash
python scripts/recover_payment_order.py --order-id order_xxx --dry-run
python scripts/recover_payment_order.py --order-id order_xxx --dry-run --check-toss
python scripts/recover_payment_order.py --order-id order_xxx --dry-run --check-toss --json
```

Preview confirm safety checks:

```bash
python scripts/recover_payment_order.py --order-id order_xxx --dry-run --confirm --json
```

Write confirmed recovery:

```bash
printf "%s\n" "$ADMIN_RECOVERY_TOKEN" | python scripts/recover_payment_order.py --order-id order_xxx --confirm --json --recovery-token-stdin
printf "%s\n" "$ADMIN_RECOVERY_TOKEN" | python scripts/recover_payment_order.py --order-id order_xxx --confirm --quiet --recovery-token-stdin
```

Write recovery, then request report generation:

```bash
printf "%s\n" "$ADMIN_RECOVERY_TOKEN" | python scripts/recover_payment_order.py --order-id order_xxx --confirm --generate-report --report-api-url https://staging-api.example.com --json --recovery-token-stdin
```

## JSON Summary

When using `--json`, check the top-level `summary` first.

```json
{
  "summary": {
    "decision": "confirm recovery written and report generation requested",
    "confirm_ready": true,
    "report_generation_requested": true,
    "report_generation_skipped": false,
    "report_generation_reason": null
  }
}
```

Most useful fields:

- `summary.decision`
- `summary.confirm_ready`
- `summary.confirm_blockers`
- `summary.report_generation_requested`
- `summary.report_generation_skipped`
- `summary.report_generation_reason`
- `summary.report_generation_guidance`

If `summary.report_generation_skipped` is true, check `summary.report_generation_reason` before retrying.

## Confirm Write Criteria

The script writes recovery data only when all of these are true:

- Toss lookup returns `DONE`.
- Toss `totalAmount` matches the pending payment amount.
- `pay:pending:{order_id}` exists and contains `analyze_request`.
- `pay:idempotency:{order_id}` does not already exist.
- No duplicate recovery lock is active.

Write order:

1. Acquire `recovery:lock:{order_id}`.
2. Re-check pending/idempotency/confirmed state.
3. Save idempotency.
4. Save confirmed payment data.
5. Delete pending.
6. Release the recovery lock.

## Report Generation

`--generate-report` does not run PDF generation directly. It calls the existing backend `/report/generate` API after confirmed recovery succeeds.

Before calling `/report/generate`, the script checks `report:record:{report_token}`:

- `ready`: skip duplicate generation and use the existing download data.
- `pending` or `generating`: skip duplicate generation and check status later.
- `error` or missing record: request `/report/generate`.

Report generation failure guidance:

- `403`: confirmed payment data was not found. Check `pay:confirmed:{report_token}` and shared Redis/storage settings.
- `404`: report endpoint or record was not found. Check `--report-api-url` and backend routing.
- `409`: report is not ready or already in progress. Check `/report/status/{report_token}` before retrying.
- `429`: wait and retry later.
- `5xx`: inspect backend report logs first, then retry after the service is healthy.

## Staging Redis Duplicate-Run Check

Run this only when staging Redis/storage credentials are configured.

```bash
printf "%s\n" "$ADMIN_RECOVERY_TOKEN" | python scripts/recover_payment_order.py --order-id order_xxx --confirm --json --recovery-token-stdin > confirm-a.json &
printf "%s\n" "$ADMIN_RECOVERY_TOKEN" | python scripts/recover_payment_order.py --order-id order_xxx --confirm --json --recovery-token-stdin > confirm-b.json &
wait
```

Expected result:

- Only one command writes recovery data.
- The other command is blocked by the recovery lock or idempotency key.
- Save `confirm-a.json` and `confirm-b.json` with the incident or staging test record.
- Check each file's top-level `summary` first.

## Toss Lookup Failures

- `400`: check `order_id` format or request parameters.
- `401`: check that `TOSS_SECRET_KEY` matches the intended Toss environment.
- `403`: check Toss account permissions and test/live key mismatch.
- `404`: Toss has no payment for the given `order_id`.
- `429`: wait and retry later.
- `5xx`: retry later and check Toss service status.
