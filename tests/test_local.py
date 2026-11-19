import sqlite3
import tempfile
import unittest
from pathlib import Path

from shelly_collector.backup import backup_database
from shelly_collector.storage import (connect, register_device, save_samples,
                                      last_channel_timestamp, claim_daily,
                                      daily_outcome, finish_daily)


class TestLocal(unittest.TestCase):
    def test_daily_guard_and_watermark(self):
        with tempfile.TemporaryDirectory() as td:
            db = connect(Path(td) / "local.sqlite3")
            device = register_device(db, {"id": "mac-em", "model": "S3EM"}, "em", "now")
            self.assertIsNone(last_channel_timestamp(db, device, 0))
            save_samples(db, device, 0, [(1795000000, 60, {"w": 42})])
            self.assertEqual(last_channel_timestamp(db, device, 0), 1795000000)
            self.assertTrue(claim_daily(db, "2026-11-19", "now"))
            self.assertFalse(claim_daily(db, "2026-11-19", "now"))
            finish_daily(db, "2026-11-19", "later", True)
            self.assertEqual(daily_outcome(db, "2026-11-19"), "success")
            db.close()

    def test_sqlite_backup(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "local.sqlite3"
            db = connect(path)
            register_device(db, {"id": "test-device", "model": "S3EM"}, "em", "now")
            destination = backup_database(path, Path(td) / "backups")
            with sqlite3.connect(str(destination)) as copy:
                self.assertEqual(copy.execute("SELECT COUNT(*) FROM devices").fetchone()[0], 1)
            db.close()


if __name__ == "__main__":
    unittest.main()
