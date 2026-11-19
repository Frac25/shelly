import unittest
from shelly_collector.diagnostic import summarize_records
from shelly_collector.http import validate_local_host


class TestDiagnostic(unittest.TestCase):
    def test_history_summary(self):
        result = summarize_records({"data_blocks": [
            {"ts": 1733299320, "period": 60, "records": 3},
            {"ts": 1733299500, "period": 300, "records": 2},
            {"ts": 0, "period": 60, "records": 1}
        ]})
        self.assertEqual(result["data_blocks_on_page"], 3)
        self.assertEqual(result["records_in_blocks_on_page"], 5)
        self.assertEqual(result["periods_seconds_on_page"], [60, 300])
        self.assertEqual(result["blocks_without_valid_clock"], 1)

    def test_host_validation(self):
        self.assertEqual(validate_local_host("192.168.1.60"), "192.168.1.60")
        with self.assertRaises(ValueError):
            validate_local_host("8.8.8.8")
        with self.assertRaises(ValueError):
            validate_local_host("127.0.0.1")


if __name__ == "__main__":
    unittest.main()
