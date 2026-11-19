"""Sauvegarde cohérente de SQLite via son API de backup (compatible Python 3.8)."""
import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime, timezone


def backup_database(source, directory):
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError("Base absente : {}".format(source))
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / ("shelly-{}.sqlite3".format(stamp))
    tmp = directory / (".shelly-{}.tmp".format(stamp))
    src = dst = None
    try:
        # mode=ro n'initialise pas silencieusement une nouvelle base.
        src = sqlite3.connect("file:{}?mode=ro".format(source.resolve()), uri=True)
        dst = sqlite3.connect(str(tmp))
        src.backup(dst, pages=100)
        result = dst.execute("PRAGMA quick_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError("Sauvegarde SQLite invalide : {}".format(result))
        dst.close()
        dst = None
        src.close()
        src = None
        os.replace(str(tmp), str(target))
        return target
    finally:
        if dst is not None:
            dst.close()
        if src is not None:
            src.close()
        if tmp.exists():
            tmp.unlink()


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    try:
        print("Sauvegarde : {}".format(backup_database(
            root / "data" / "local.sqlite3", root / "data" / "backups")))
    except (OSError, sqlite3.Error, RuntimeError) as err:
        print("Erreur de sauvegarde : {}".format(err), file=sys.stderr)
        sys.exit(1)
