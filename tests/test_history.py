import json
import tempfile
import unittest
from pathlib import Path
from shelly_collector.history import normalize_data, blocks_from_records, collect_channel
from unittest.mock import patch
from shelly_collector.storage import connect, register_device, save_samples, save_snapshot, stats
from shelly_collector.exporters import export_all

class TestHistory(unittest.TestCase):
    def test_normalize_sequential_timestamps(self):
        response = {"keys": ["total_act_energy", "avg_voltage"],
           "data": [{"ts": 1795000000, "period":60, "values": [[1.2,230.5],[1.6,229.9]]}]}
        result = normalize_data(response, 1795000000, 1795000099)
        self.assertEqual([r[0] for r in result], [1795000000,1795000060])
        self.assertEqual(result[1][2], {"total_act_energy":1.6,"avg_voltage":229.9})

    def test_invalid_column_count_detected(self):
        with self.assertRaises(ValueError):
            normalize_data({"keys":["a","b"], "data":[{"ts":1795000000,"period":60,"values":[[2]]}]}, 1795000000,1795000000)

    def test_bad_block_rejected(self):
        with self.assertRaises(ValueError):
            blocks_from_records({"data_blocks":[{"ts":0,"period":0,"records":1}]})

    def test_pagination_without_next_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            db = connect(Path(folder)/"a.db")
            identity = {"id":"sample", "model":"S3EM"}
            register_device(db, identity, "sample", "2026-11-19T00:00:00Z")
            requests = []
            def mock_http(host, path, params, timeout=15):
                requests.append(params["ts"])
                if len(requests) == 1:
                    return {"keys":["x"],"data":[{"ts":1795000000,"period":60,"values":[[1],[2]]}]}
                return {"keys":["x"],"data":[{"ts":1795000120,"period":60,"values":[[3]]}]}
            with patch("shelly_collector.history.get_json", side_effect=mock_http):
                count, windows, _ = collect_channel(db,"192.168.1.60","sample",0,
                    1795000000,1795000200,False)
            self.assertEqual(count,3)
            self.assertEqual(windows,3)
            self.assertEqual(stats(db)["history_records"],3)
            db.close()

    def test_idempotent_upsert_and_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            db = connect(Path(folder)/"local.db")
            device_id=register_device(db,{"id":"shelly-em-test", "model":"S3EM"},"em_test","2026-11-19T14:00:00+00:00")
            samples=[(1795000000,60,{"energy_wh":5.2}), (1795000060,60,{"energy_wh":5.4})]
            self.assertEqual(save_samples(db,device_id,0,samples),2)
            self.assertEqual(save_samples(db,device_id,0,samples),0)
            self.assertEqual(save_samples(db,device_id,0,[(1795000000,60,{"energy_wh":5.3})]),1)
            self.assertTrue(save_snapshot(db,device_id,"2026-11-19","2026-11-19T14:00:00Z",{"switch:0":{"output":False}}))
            self.assertFalse(save_snapshot(db,device_id,"2026-11-19","2026-11-19T14:10:00Z",{"switch:0":{"output":True}}))
            self.assertEqual(stats(db)["history_records"],2)
            export_dir=Path(folder)/"exports"
            counts=export_all(db,export_dir)
            self.assertEqual(counts["historique"],2)
            self.assertIn("energy_wh", (export_dir/"historique.csv").read_text(encoding="utf-8-sig"))
            db.close()

if __name__ == "__main__":
    unittest.main()
