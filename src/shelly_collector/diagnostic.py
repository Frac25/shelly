"""Résumé strictement non destructif des capacités et historiques des Shelly."""
from datetime import datetime, timezone
import re

from .http import ShellyConnectionError, get_json

COMPONENT_RE = re.compile(r"^[a-z][a-z0-9_]*:[0-9]+$")
HISTORY_RE = re.compile(r"^em1data:([0-9]+)$")


def iso_utc(unix_ts):
    if not isinstance(unix_ts, (int, float)) or unix_ts < 946684800:
        return None
    try:
        return datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def summarize_records(records):
    """Résume la page de blocs disponible, sans supposer que c'est l'historique complet."""
    blocks = records.get("data_blocks", [])
    if not isinstance(blocks, list):
        blocks = []
    valid = []
    unclocked = 0
    for block in blocks:
        if not isinstance(block, dict):
            continue
        ts = block.get("ts")
        period = block.get("period")
        count = block.get("records")
        if (isinstance(ts, (int, float)) and isinstance(period, (int, float))
                and isinstance(count, int) and count > 0 and period > 0):
            if iso_utc(ts):
                valid.append((ts, ts + (count - 1) * period, period, count))
            else:
                unclocked += 1
    return {
        "data_blocks_on_page": len(blocks),
        "records_in_blocks_on_page": sum(item[3] for item in valid),
        "blocks_without_valid_clock": unclocked,
        "first_timestamp_utc_on_page": iso_utc(min(item[0] for item in valid)) if valid else None,
        "last_timestamp_utc_on_page": iso_utc(max(item[1] for item in valid)) if valid else None,
        "periods_seconds_on_page": sorted(set(item[2] for item in valid)),
        "next_record_ts": records.get("next_record_ts"),
        "note": "Première page seulement; pas encore d'import des données elles-mêmes."
    }


def diagnostic_device(device):
    host = device["host"]
    result = {
        "alias": device["alias"], "host": host,
        "description": device.get("description", ""),
        "identity": None, "components": [], "history": {}, "errors": []
    }
    try:
        identity = get_json(host, "/shelly")
        result["identity"] = {key: identity.get(key) for key in ("id", "name", "model", "gen", "ver", "auth_en")}
    except (ShellyConnectionError, ValueError) as exc:
        result["errors"].append("/shelly: {}".format(exc))
        return result

    try:
        status = get_json(host, "/rpc/Shelly.GetStatus")
        result["components"] = sorted(key for key in status.keys() if COMPONENT_RE.match(key))
    except (ShellyConnectionError, ValueError) as exc:
        result["errors"].append("Shelly.GetStatus: {}".format(exc))

    channels = sorted(int(HISTORY_RE.match(item).group(1)) for item in result["components"] if HISTORY_RE.match(item))
    # Certains firmwares ne retournent pas tous les composants dans GetStatus.
    # Les deux modèles d'EM identifiés exposent normalement deux canaux d'historique.
    if result["identity"].get("model") in ("S3EM-002CXCEU", "S4EM-002CXCEU") and not channels:
        channels = [0, 1]

    for channel in channels:
        label = "em1data:{}".format(channel)
        try:
            records = get_json(host, "/rpc/EM1Data.GetRecords", {"id": channel, "ts": 0})
            result["history"][label] = summarize_records(records)
        except (ShellyConnectionError, ValueError) as exc:
            result["history"][label] = {"error": str(exc)}
    return result


def current_utc():
    return datetime.now(timezone.utc).isoformat()
