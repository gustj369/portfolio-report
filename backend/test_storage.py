import unittest

from services import storage


class StorageLockTest(unittest.TestCase):
    def setUp(self):
        storage._local.clear()

    def tearDown(self):
        storage._local.clear()

    def test_local_lock_acquire_blocks_duplicate_owner(self):
        self.assertTrue(storage.storage_acquire_lock("lock:test", "owner-1", ttl=60))
        self.assertFalse(storage.storage_acquire_lock("lock:test", "owner-1", ttl=60))

    def test_local_lock_release_requires_same_owner(self):
        self.assertTrue(storage.storage_acquire_lock("lock:test", "owner-1", ttl=60))
        self.assertFalse(storage.storage_release_lock("lock:test", "owner-2"))
        self.assertTrue(storage.storage_release_lock("lock:test", "owner-1"))
        self.assertTrue(storage.storage_acquire_lock("lock:test", "owner-2", ttl=60))

    def test_local_payment_recovery_confirm_writes_in_safe_order(self):
        storage.storage_set("pay:pending:order_test", {"amount": 4900}, ttl=60)

        result = storage.storage_confirm_payment_recovery(
            order_id="order_test",
            report_token="rpt_test",
            confirmed_record={"order_id": "order_test", "amount": 4900},
            idempotency_record={"report_token": "rpt_test"},
            ttl=60,
        )

        self.assertTrue(result["ok"])
        self.assertIsNone(storage.storage_get("pay:pending:order_test"))
        self.assertEqual(storage.storage_get("pay:idempotency:order_test")["report_token"], "rpt_test")
        self.assertEqual(storage.storage_get("pay:confirmed:rpt_test")["order_id"], "order_test")

    def test_local_payment_recovery_confirm_blocks_duplicate(self):
        storage.storage_set("pay:pending:order_test", {"amount": 4900}, ttl=60)
        storage.storage_set("pay:idempotency:order_test", {"report_token": "rpt_old"}, ttl=60)

        result = storage.storage_confirm_payment_recovery(
            order_id="order_test",
            report_token="rpt_new",
            confirmed_record={"order_id": "order_test", "amount": 4900},
            idempotency_record={"report_token": "rpt_new"},
            ttl=60,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "idempotency exists")
        self.assertIsNone(storage.storage_get("pay:confirmed:rpt_new"))


if __name__ == "__main__":
    unittest.main()
