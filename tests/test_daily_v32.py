"""Tests ciblés V3.2, sans HTTP ni réseau."""
import argparse
import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from shelly_collector.cli import main, run_collection
from shelly_collector.exporters import csv_stream
from shelly_collector.history import MIN_VALID_TS
from shelly_collector.http import ShellyConnectionError
from shelly_collector.storage import (connect, daily_device_outcome, daily_outcome,
                                      register_device, save_samples, stats)


class DummySocket:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestDailyResilience(unittest.TestCase):
    def test_partial_failure_retry_only_failed_device_and_exports(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            cfg = folder / "devices.json"
            cfg.write_text(json.dumps({"devices": [
                {"alias": "A", "host": "192.168.1.60"},
                {"alias": "B", "host": "192.168.1.58"},
            ]}))
            db_path = folder / "db.sqlite3"
            exports = folder / "exports"
            calls = []
            failing = {"B"}

            def fake_http(host, path):
                alias = "A" if host.endswith("60") else "B"
                calls.append((alias, path))
                if alias in failing:
                    raise ShellyConnectionError("hors ligne")
                if path == "/shelly":
                    return {"id": alias, "model": "S4SW"}
                if path == "/rpc/Shelly.GetStatus":
                    return {"switch:0": {"output": True}}
                raise AssertionError(path)

            def run():
                return main(["daily", "--config", str(cfg),
                             "--db", str(db_path), "--exports", str(exports)])

            with patch("socket.create_connection", return_value=DummySocket()), \
                 patch("shelly_collector.cli.get_json", side_effect=fake_http):
                self.assertEqual(run(), 1)
                with connect(db_path) as db:
                    day = datetime.now().astimezone().date().isoformat()
                    self.assertEqual(daily_outcome(db, day), "failed")
                    self.assertEqual(daily_device_outcome(db, day, "A"), "success")
                    self.assertEqual(daily_device_outcome(db, day, "B"), "failed")
                    self.assertEqual(stats(db)["daily_snapshots"], 1)
                self.assertTrue((exports / "etats_quotidiens.csv").exists())
                a_calls = len([c for c in calls if c[0] == "A"])
                failing.clear()
                self.assertEqual(run(), 0)
                self.assertEqual(len([c for c in calls if c[0] == "A"]), a_calls)
                with connect(db_path) as db:
                    self.assertEqual(daily_outcome(db, day), "success")
                    self.assertEqual(stats(db)["daily_snapshots"], 2)
                with (exports / "etats_quotidiens.csv").open(encoding="utf-8-sig", newline="") as f:
                    self.assertEqual(len(list(csv.DictReader(f, delimiter=";"))), 2)
                count_before = len(calls)
                self.assertEqual(run(), 0)
                self.assertEqual(len(calls), count_before)

    def test_catchup_uses_old_watermark_without_30_day_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            db = connect(Path(folder) / "db.sqlite3")
            now = int(datetime.now(timezone.utc).timestamp())
            older = now - 45 * 86400
            device_id = register_device(db, {"id": "EM", "model": "S4EM"}, "em", "now")
            save_samples(db, device_id, 0, [(older, 60, {"w": 100})])
            windows = []

            def fake_http(host, path):
                if path == "/shelly":
                    return {"id": "EM", "model": "S4EM"}
                return {"em1data:0": {}, "em1data:1": {}}

            def fake_collect(db, host, device, channel, since, until, all_available):
                windows.append((channel, since, all_available))
                return (0, 0, 0)

            args = argparse.Namespace(command="daily", days=7, since=None, until=None, all_available=False)
            with patch("shelly_collector.cli.get_json", side_effect=fake_http), \
                 patch("shelly_collector.cli.collect_channel", side_effect=fake_collect):
                self.assertEqual(run_collection(db, [{"alias": "em", "host": "192.168.1.41"}],
                                                args, daily_day="2026-11-20"), 0)
            self.assertEqual(windows[0], (0, older - 7200, True))
            self.assertEqual(windows[1], (1, MIN_VALID_TS, True))
            db.close()

    def test_export_failure_is_retryable_without_second_device_read(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            cfg = folder / "devices.json"
            cfg.write_text(json.dumps({"devices": [{"alias": "A", "host": "192.168.1.60"}]}))
            db_path = folder / "db.sqlite3"
            calls = []
            failure = {"active": True}

            def fake_http(host, path):
                calls.append(path)
                if path == "/shelly":
                    return {"id": "A", "model": "S4SW"}
                return {"switch:0": {"output": False}}

            from shelly_collector.exporters import export_all as real_export

            def maybe_export(db, directory):
                if failure["active"]:
                    raise OSError("disque plein")
                return real_export(db, directory)

            args = ["daily", "--config", str(cfg), "--db", str(db_path),
                    "--exports", str(folder / "exports")]
            with patch("socket.create_connection", return_value=DummySocket()), \
                 patch("shelly_collector.cli.get_json", side_effect=fake_http), \
                 patch("shelly_collector.cli.export_all", side_effect=maybe_export):
                self.assertEqual(main(args), 1)
                calls_first = len(calls)
                failure["active"] = False
                self.assertEqual(main(args), 0)
                self.assertEqual(len(calls), calls_first)
                self.assertTrue((folder / "exports" / "etats_quotidiens.csv").exists())

    def test_manual_collect_updates_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            cfg = folder / "devices.json"
            cfg.write_text(json.dumps({"devices": [{"alias": "chaudiere", "host": "192.168.1.58"}]}))

            def fake_http(host, path):
                if path == "/shelly":
                    return {"id": "R", "model": "S4SW"}
                return {"switch:0": {"output": True}}

            output = folder / "exports"
            with patch("shelly_collector.cli.get_json", side_effect=fake_http):
                self.assertEqual(main(["collect", "--config", str(cfg),
                    "--db", str(folder / "db.sqlite3"), "--exports", str(output)]), 0)
            with (output / "etats_quotidiens.csv").open(encoding="utf-8-sig", newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f, delimiter=";"))), 1)

    def test_channel_error_keeps_device_retryable(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            cfg = folder / "devices.json"
            cfg.write_text(json.dumps({"devices": [{"alias": "em", "host": "192.168.1.41"}]}))
            failed = {"channel1": True}
            calls = []

            def fake_http(host, path):
                if path == "/shelly":
                    return {"id": "EM", "model": "S4EM"}
                return {"em1data:0": {}, "em1data:1": {}}

            def fake_collect(db, host, device, channel, since, until, all_available):
                calls.append(channel)
                if channel == 1 and failed["channel1"]:
                    raise ShellyConnectionError("canal indisponible")
                return (0, 0, 0)

            args = ["daily", "--config", str(cfg), "--db", str(folder / "db.sqlite3"),
                    "--exports", str(folder / "exports")]
            with patch("socket.create_connection", return_value=DummySocket()), \
                 patch("shelly_collector.cli.get_json", side_effect=fake_http), \
                 patch("shelly_collector.cli.collect_channel", side_effect=fake_collect):
                self.assertEqual(main(args), 1)
                failed["channel1"] = False
                self.assertEqual(main(args), 0)
            self.assertEqual(calls, [0, 1, 0, 1])
            db = connect(folder / "db.sqlite3")
            day = datetime.now().astimezone().date().isoformat()
            self.assertEqual(daily_device_outcome(db, day, "em"), "success")
            db.close()

    def test_csv_previous_version_survives_write_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "data.csv"
            dest.write_text("ancien fichier\n", encoding="utf-8")

            def broken_rows():
                yield {"x": 1}
                raise OSError("écriture interrompue")

            with self.assertRaises(OSError):
                csv_stream(dest, ["x"], broken_rows())
            self.assertEqual(dest.read_text(encoding="utf-8"), "ancien fichier\n")
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ["data.csv"])


if __name__ == "__main__":
    unittest.main()
