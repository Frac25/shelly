"""Exports CSV Excel depuis SQLite, sans charger les mesures en mémoire."""
import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def flatten(obj, prefix=""):
    result = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = (prefix + "." if prefix else "") + str(key)
            result.update(flatten(value, path))
    else:
        result[prefix] = json.dumps(obj, ensure_ascii=False) if isinstance(obj, list) else obj
    return result


def csv_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return str(value).replace(".", ",")  # Excel français
    return value


def csv_stream(path, columns, rows):
    """Écrire un CSV temporaire, puis le remplacer atomiquement si complet."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".{}-".format(path.name), suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, delimiter=";", extrasaction="ignore")
            writer.writeheader()
            count = 0
            for row in rows:
                writer.writerow({key: csv_value(value) for key, value in row.items()})
                count += 1
        os.replace(temporary, str(path))
        return count
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def export_all(db, directory):
    directory = Path(directory)
    hist_query = """SELECT h.device_id, d.alias, h.channel, h.timestamp_utc,
       h.period_s, h.values_json FROM history h
       JOIN devices d ON d.device_id=h.device_id
       ORDER BY h.timestamp_utc, h.device_id, h.channel"""
    hist_columns = ["appareil", "device_id", "canal", "horodatage_utc", "periode_s"]
    dynamic = set()
    for (raw,) in db.execute("SELECT values_json FROM history"):
        dynamic.update(json.loads(raw).keys())
    hist_columns.extend(sorted(dynamic - set(hist_columns)))

    def history_rows():
        for device_id, alias, channel, ts, period, raw in db.execute(hist_query):
            row = {"appareil": alias, "device_id": device_id, "canal": channel,
                   "horodatage_utc": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                   "periode_s": period}
            row.update(json.loads(raw))
            yield row
    history_count = csv_stream(directory / "historique.csv", hist_columns, history_rows())

    snap_query = """SELECT s.device_id, d.alias, s.local_day, s.captured_at_utc,
       s.status_json FROM snapshots s JOIN devices d ON d.device_id=s.device_id
       ORDER BY s.local_day, s.device_id"""
    snap_columns = ["appareil", "device_id", "jour_local", "date_lecture_utc"]
    dynamic = set()
    for (raw,) in db.execute("SELECT status_json FROM snapshots"):
        dynamic.update(flatten(json.loads(raw)).keys())
    snap_columns.extend(sorted(dynamic - set(snap_columns)))

    def snapshot_rows():
        for device_id, alias, day, captured, raw in db.execute(snap_query):
            row = {"appareil": alias, "device_id": device_id, "jour_local": day,
                   "date_lecture_utc": captured}
            row.update(flatten(json.loads(raw)))
            yield row
    snapshot_count = csv_stream(directory / "etats_quotidiens.csv", snap_columns, snapshot_rows())

    cols = ["device_id", "canal", "timestamp_unix", "periode_s", "nombre", "raison"]
    def suspect_rows():
        for record in db.execute("""SELECT device_id, channel, timestamp_utc,
                   period_s, records, reason FROM suspect_blocks
                   ORDER BY device_id, channel, timestamp_utc"""):
            yield dict(zip(cols, record))
    suspect_count = csv_stream(directory / "blocs_suspects.csv", cols, suspect_rows())
    return {"historique": history_count, "etats_quotidiens": snapshot_count,
            "blocs_suspects": suspect_count}
