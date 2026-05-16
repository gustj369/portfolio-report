import unittest

from services.observability import init_sentry


class ObservabilityTest(unittest.TestCase):
    def test_sentry_without_dsn_is_disabled(self):
        self.assertFalse(init_sentry(dsn=""))


if __name__ == "__main__":
    unittest.main()
