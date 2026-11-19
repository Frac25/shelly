"""Lecture non destructive de EM1Data : pagination + contrôle d'horloge."""
import time
from datetime import datetime, timezone
from .http import get_json
from .storage import save_samples, save_suspect

MIN_VALID_TS = 1577836800  # 2020-01-01 UTC : limite prudente, configurable dans le futur
MAX_WINDOWS = 3000
STEP_S = 3600   # Fenêtres d'une heure pour éviter les réponses HTTP trop volumineuses


def blocks_from_records(payload):
    blocks = payload.get("data_blocks", [])
    if not isinstance(blocks, list):
        raise ValueError("GetRecords.data_blocks n'est pas une liste")
    valid = []
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("Bloc historique invalide")
        ts, period, records = block.get("ts"), block.get("period"), block.get("records")
        if not all(type(n) is int for n in (ts, period, records)) or period <= 0 or records <= 0:
            raise ValueError("Métadonnées de bloc incorrectes : {}".format(block))
        valid.append({"ts": ts, "period": period, "records": records})
    return valid


def discover_blocks(host, channel, max_pages=100):
    """Pagine GetRecords en utilisant ts; s'arrête si plus de progression."""
    blocks = {}
    cursor = 0
    pages_seen = set()
    for _ in range(max_pages):
        result = get_json(host, "/rpc/EM1Data.GetRecords", {"id": channel, "ts": cursor})
        page = blocks_from_records(result)
        if not page:
            break
        signature = tuple((b["ts"], b["period"], b["records"]) for b in page)
        if signature in pages_seen:
            break
        pages_seen.add(signature)
        for b in page:
            blocks[(b["ts"], b["period"], b["records"])] = b
        # GetRecords accepte ts pour atteindre la prochaine page, mais
        # certains firmwares retournent tous les blocs dès le premier appel.
        next_cursor = max(b["ts"] + b["period"] * b["records"] for b in page)
        explicit = result.get("next_record_ts")
        if type(explicit) is int and explicit > cursor:
            next_cursor = explicit
        if next_cursor <= cursor:
            break
        cursor = next_cursor
    else:
        raise ValueError("Trop de pages GetRecords; arrêt préventif")
    return sorted(blocks.values(), key=lambda b: b["ts"])


def normalize_data(payload, start, end):
    """Chaque entrée de values est une minute/une période successive."""
    keys = payload.get("keys")
    chunks = payload.get("data")
    if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
        raise ValueError("GetData.keys absent ou incorrect")
    if not isinstance(chunks, list):
        raise ValueError("GetData.data absent ou incorrect")
    samples = []
    for block in chunks:
        if not isinstance(block, dict):
            raise ValueError("GetData.data contient un bloc non objet")
        ts, period, rows = block.get("ts"), block.get("period"), block.get("values")
        if type(ts) is not int or type(period) is not int or period <= 0 or not isinstance(rows, list):
            raise ValueError("Bloc GetData non conforme")
        for index, vals in enumerate(rows):
            current_ts = ts + index * period
            if not isinstance(vals, list) or len(vals) != len(keys):
                raise ValueError("Mesure avec colonnes manquantes : {} vs {}".format(len(vals) if isinstance(vals,list) else "?", len(keys)))
            if start <= current_ts <= end and MIN_VALID_TS <= current_ts <= int(time.time()) + 86400:
                samples.append((current_ts, period, dict(zip(keys, vals))))
    return samples


def collect_channel(db, host, device_id, channel, since_ts, until_ts,
                    all_available=False):
    """Retourne compteurs; seules des lectures RPC GET sont effectuées."""
    if all_available:
        blocks = discover_blocks(host, channel)
    else:
        # Une fenêtre explicite est suffisante, sans accès préalable à GetRecords.
        blocks = [{"ts": since_ts, "period": 60,
                   "records": max(1, (until_ts - since_ts) // 60 + 1)}]
    changed = 0
    windows = 0
    ignored_blocks = 0
    now = int(time.time())
    for block in blocks:
        start = block["ts"]
        last = start + (block["records"] - 1) * block["period"]
        if start < MIN_VALID_TS or start > now + 86400 or last > now + 86400:
            ignored_blocks += 1
            save_suspect(db, device_id, channel, block, "horodatage suspect")
            continue
        start = max(start, since_ts)
        last = min(last, until_ts)
        if last < start:
            continue
        cursor = start
        while cursor <= last:
            windows += 1
            if windows > MAX_WINDOWS:
                raise ValueError("Nombre maximal de fenêtres atteint, préciser une plage de dates")
            request_end = min(last, cursor + STEP_S - 1)
            payload = get_json(host, "/rpc/EM1Data.GetData",
                {"id": channel, "ts": cursor, "end_ts": request_end}, timeout=15)
            samples = normalize_data(payload, cursor, request_end)
            changed += save_samples(db, device_id, channel, samples)
            hint = payload.get("next_record_ts")
            if type(hint) is int and cursor < hint <= request_end:
                cursor = hint
            elif samples:
                # Certains firmwares peuvent limiter le nombre de lignes renvoyées.
                # Si la réponse s'arrête avant la fin demandée, continuer plus loin.
                last_ts, last_period, _ = max(samples, key=lambda item: item[0])
                candidate = last_ts + last_period
                cursor = candidate if cursor < candidate <= request_end else request_end + 1
            else:
                cursor = request_end + 1
    return changed, windows, ignored_blocks


def iso_from_ts(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()
