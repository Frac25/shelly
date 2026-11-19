"""SQLite local : base de référence sur Mac; exportable ultérieurement."""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    alias TEXT NOT NULL,
    model TEXT NOT NULL,
    last_seen_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history (
    device_id TEXT NOT NULL,
    channel INTEGER NOT NULL,
    timestamp_utc INTEGER NOT NULL,
    period_s INTEGER NOT NULL,
    values_json TEXT NOT NULL,
    PRIMARY KEY (device_id, channel, timestamp_utc, period_s),
    FOREIGN KEY (device_id) REFERENCES devices(device_id)
);
CREATE INDEX IF NOT EXISTS idx_history_time ON history(timestamp_utc);
CREATE TABLE IF NOT EXISTS snapshots (
    device_id TEXT NOT NULL,
    local_day TEXT NOT NULL,
    captured_at_utc TEXT NOT NULL,
    status_json TEXT NOT NULL,
    PRIMARY KEY (device_id, local_day),
    FOREIGN KEY (device_id) REFERENCES devices(device_id)
);
CREATE TABLE IF NOT EXISTS daily_runs (
    local_day TEXT PRIMARY KEY,
    started_at_utc TEXT NOT NULL,
    finished_at_utc TEXT,
    outcome TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_device_runs (
    local_day TEXT NOT NULL,
    device_alias TEXT NOT NULL,
    outcome TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY (local_day, device_alias)
);
CREATE TABLE IF NOT EXISTS suspect_blocks (
    device_id TEXT NOT NULL,
    channel INTEGER NOT NULL,
    timestamp_utc INTEGER NOT NULL,
    period_s INTEGER NOT NULL,
    records INTEGER NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY (device_id, channel, timestamp_utc, period_s, records)
);
"""


def connect(db_path):
    target = Path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(target), timeout=20)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA)
    return db


def register_device(db, identity, alias, now_utc):
    device_id = identity.get("id")
    if not isinstance(device_id, str) or not device_id:
        raise ValueError("Shelly /shelly ne fournit aucun ID stable")
    model = str(identity.get("model") or "unknown")
    with db:
        db.execute("""INSERT INTO devices(device_id, alias, model, last_seen_utc)
                      VALUES (?, ?, ?, ?)
                      ON CONFLICT(device_id) DO UPDATE SET
                        alias=excluded.alias, model=excluded.model,
                        last_seen_utc=excluded.last_seen_utc""",
                   (device_id, alias, model, now_utc))
    return device_id


def save_snapshot(db, device_id, day, captured_at, status):
    raw = json.dumps(status, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    with db:
        cursor = db.execute("""INSERT OR IGNORE INTO snapshots
                (device_id, local_day, captured_at_utc, status_json) VALUES (?, ?, ?, ?)""",
                (device_id, day, captured_at, raw))
    return cursor.rowcount > 0


def save_samples(db, device_id, channel, samples):
    """Relevés idempotents : une correction Shelly peut remplacer la valeur existante."""
    if not samples:
        return 0
    changed = 0
    with db:
        for ts, period, values in samples:
            raw = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            cursor = db.execute("""INSERT INTO history
               (device_id, channel, timestamp_utc, period_s, values_json)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(device_id, channel, timestamp_utc, period_s)
               DO UPDATE SET values_json=excluded.values_json
               WHERE history.values_json <> excluded.values_json""",
                (device_id, channel, ts, period, raw))
            changed += cursor.rowcount
    return changed


def save_suspect(db, device_id, channel, block, reason):
    with db:
        db.execute("""INSERT OR IGNORE INTO suspect_blocks
            (device_id, channel, timestamp_utc, period_s, records, reason)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (device_id, channel, block["ts"], block["period"], block["records"], reason))


def last_channel_timestamp(db, device_id, channel):
    return db.execute("""SELECT MAX(timestamp_utc) FROM history
                       WHERE device_id=? AND channel=?""",
                      (device_id, channel)).fetchone()[0]


def claim_daily(db, day, started_at):
    """Un succès quotidien est définitif ; un échec/crash peut être repris.

    Le verrou inter-processus est pris par la CLI avant cet appel.
    """
    with db:
        row = db.execute("""INSERT INTO daily_runs
              (local_day, started_at_utc, finished_at_utc, outcome)
              VALUES (?, ?, NULL, 'running')
              ON CONFLICT(local_day) DO UPDATE SET
                started_at_utc=excluded.started_at_utc,
                finished_at_utc=NULL, outcome='running'
              WHERE daily_runs.outcome <> 'success'""", (day, started_at))
        return row.rowcount == 1


def daily_device_outcome(db, day, alias):
    row = db.execute("""SELECT outcome FROM daily_device_runs
                        WHERE local_day=? AND device_alias=?""", (day, alias)).fetchone()
    return row[0] if row else None


def mark_daily_device(db, day, alias, success, when):
    with db:
        db.execute("""INSERT INTO daily_device_runs
            (local_day, device_alias, outcome, updated_at_utc)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(local_day, device_alias) DO UPDATE SET
              outcome=excluded.outcome, updated_at_utc=excluded.updated_at_utc""",
            (day, alias, 'success' if success else 'failed', when))


def finish_daily(db, day, finished_at, ok):
    with db:
        db.execute("""UPDATE daily_runs SET finished_at_utc=?, outcome=?
                      WHERE local_day=?""",
                   (finished_at, 'success' if ok else 'failed', day))


def daily_outcome(db, day):
    row = db.execute("SELECT outcome FROM daily_runs WHERE local_day=?", (day,)).fetchone()
    return row[0] if row else None


def stats(db):
    return {
        "devices": db.execute("SELECT COUNT(*) FROM devices").fetchone()[0],
        "history_records": db.execute("SELECT COUNT(*) FROM history").fetchone()[0],
        "daily_snapshots": db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0],
        "suspect_blocks": db.execute("SELECT COUNT(*) FROM suspect_blocks").fetchone()[0],
        "daily_runs": db.execute("SELECT COUNT(*) FROM daily_runs").fetchone()[0],
    }
