"""Interface de commande du collecteur Shelly. Aucune tâche planifiée ici."""
import argparse
import json
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone

from .diagnostic import current_utc, diagnostic_device
from .exporters import export_all
from .history import collect_channel, iso_from_ts
from .http import ShellyConnectionError, get_json, validate_local_host
from .storage import (connect, register_device, save_snapshot, stats,
                      last_channel_timestamp, claim_daily, finish_daily, daily_outcome)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "devices.json"
DEFAULT_DIAGNOSTIC = ROOT / "data" / "diagnostic.json"
DEFAULT_DB = ROOT / "data" / "local.sqlite3"
DEFAULT_EXPORTS = ROOT / "data" / "exports"


def load_devices(path):
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    devices = payload.get("devices", [])
    if not isinstance(devices, list) or not devices:
        raise ValueError("La liste 'devices' doit être non vide")
    names = set()
    for item in devices:
        if not isinstance(item, dict) or not item.get("alias") or not item.get("host"):
            raise ValueError("Chaque appareil doit avoir 'alias' et 'host'")
        if item["alias"] in names:
            raise ValueError("Alias dupliqué : {}".format(item["alias"]))
        names.add(item["alias"])
        validate_local_host(item["host"])
    return devices


def date_to_utc(date_text):
    return int(datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def select_window(args):
    now = int(datetime.now(timezone.utc).timestamp())
    if args.all_available:
        since = date_to_utc("2020-01-01")
    elif args.since:
        since = date_to_utc(args.since)
    else:
        if args.days <= 0 or args.days > 365:
            raise ValueError("--days doit être compris entre 1 et 365")
        since = now - int(args.days * 86400)
    # --until est une date EXCLUSIVE en UTC, pratique pour un intervalle précis.
    until = date_to_utc(args.until) - 1 if args.until else now
    if since > until:
        raise ValueError("Plage vide : vérifier --since et --until (exclusif)")
    if until > now + 86400:
        raise ValueError("La fin de plage ne doit pas dépasser demain")
    return since, until


def do_audit(devices, output):
    report = {"diagnostic_utc": current_utc(), "mode": "read_only", "devices": []}
    failures = 0
    for item in devices:
        print("\n--- {} ({}) ---".format(item["alias"], item["host"]))
        result = diagnostic_device(item)
        report["devices"].append(result)
        identity = result["identity"] or {}
        print("Modèle : {} | Gen {} | Firmware {}".format(identity.get("model", "?"), identity.get("gen", "?"), identity.get("ver", "?")))
        print("Composants : {}".format(", ".join(result["components"]) or "non disponibles"))
        for label, summary in sorted(result["history"].items()):
            if "error" in summary:
                print("Historique {} : erreur : {}".format(label, summary["error"]))
            else:
                print("Historique {} : {} bloc(s) visibles, période(s) {} s, du {} au {} (UTC)".format(
                    label, summary["data_blocks_on_page"], summary["periods_seconds_on_page"],
                    summary["first_timestamp_utc_on_page"], summary["last_timestamp_utc_on_page"]))
        for err in result["errors"]:
            print("ATTENTION : {}".format(err))
        if result["errors"] or any("error" in entry for entry in result["history"].values()):
            failures += 1
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\nDiagnostic enregistré dans {}".format(target))
    return 1 if failures else 0


def run_collection(db, devices, args):
    do_history = args.command in ("history", "collect", "daily")
    do_snapshot = args.command in ("snapshot", "collect", "daily")
    if do_history:
        since, until = select_window(args)
        print("Historique : {} à {} UTC".format(iso_from_ts(since), iso_from_ts(until)))
    failures = 0
    for device in devices:
        print("\n--- {} ({}) ---".format(device["alias"], device["host"]))
        try:
            identity = get_json(device["host"], "/shelly")
            device_id = register_device(db, identity, device["alias"], current_utc())
            status = get_json(device["host"], "/rpc/Shelly.GetStatus")
            if do_snapshot:
                # Date macOS locale (Europe/Paris si la zone système est réglée ainsi).
                local_day = datetime.now().astimezone().date().isoformat()
                added = save_snapshot(db, device_id, local_day, current_utc(), status)
                print("État du jour : {}".format("enregistré" if added else "déjà présent, aucun doublon"))
            if do_history:
                channels = sorted(int(k.split(":")[1]) for k in status
                    if k.startswith("em1data:") and k.split(":")[1].isdigit())
                if not channels:
                    print("Aucun composant EM1Data : pas d'historique minute par cette API")
                for channel in channels:
                    try:
                        channel_since = since
                        if args.command == "daily":
                            latest = last_channel_timestamp(db, device_id, channel)
                            if latest is not None:
                                # 2h de recouvrement corrigent les dernières données
                                # sans relire systématiquement sept jours.
                                channel_since = min(until, max(until - 30 * 86400, latest - 7200))
                                if latest < until - 30 * 86400:
                                    print("ATTENTION canal {} : historique > 30 jours ; "
                                          "rattrapage partiel uniquement".format(channel))
                            print("Canal {} : reprise depuis {}".format(channel,
                                iso_from_ts(channel_since)))
                        changed, windows, suspect = collect_channel(db, device["host"], device_id,
                            channel, channel_since, until, all_available=args.all_available)
                        print("Canal {} : {} ligne(s) nouvelles/corrigées, {} appels GetData, {} bloc(s) suspects".format(
                            channel, changed, windows, suspect))
                    except (ShellyConnectionError, ValueError, OSError) as exc:
                        print("ERREUR {} canal {} : {}".format(device["alias"], channel, exc), file=sys.stderr)
                        failures += 1
        except (ShellyConnectionError, ValueError, OSError) as exc:
            print("ERREUR {} : {}".format(device["alias"], exc), file=sys.stderr)
            failures += 1
    return 1 if failures else 0


def coverage(db):
    """Contrôle simple de continuité par canal, sans modifier les mesures."""
    rows = db.execute("""SELECT d.alias, h.channel, COUNT(*), MIN(h.timestamp_utc),
             MAX(h.timestamp_utc) FROM history h JOIN devices d USING(device_id)
             GROUP BY h.device_id, h.channel ORDER BY d.alias, h.channel""").fetchall()
    if not rows:
        print("Aucune mesure historique enregistrée")
        return
    for alias, channel, count, first, last in rows:
        gaps = 0
        previous_ts = previous_period = None
        for ts, period in db.execute("""SELECT h.timestamp_utc,h.period_s
             FROM history h JOIN devices d USING(device_id)
             WHERE d.alias=? AND h.channel=? ORDER BY h.timestamp_utc""", (alias, channel)):
            if previous_ts is not None and ts > previous_ts + previous_period:
                gaps += 1
            previous_ts, previous_period = ts, period
        print("{} / canal {} : {} lignes, {} à {}, {} intervalle(s) manquant(s)".format(
            alias, channel, count, iso_from_ts(first), iso_from_ts(last), gaps))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Shelly : diagnostic + historique SQLite local")
    parser.add_argument("command", choices=("list", "audit", "snapshot", "history", "collect", "daily", "export", "stats", "coverage"))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", default=str(DEFAULT_DIAGNOSTIC), help="Fichier audit")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--exports", default=str(DEFAULT_EXPORTS))
    parser.add_argument("--device", help="Limiter à un alias du fichier de configuration")
    parser.add_argument("--days", type=int, default=7, help="Plage glissante en jours UTC (défaut : 7)")
    parser.add_argument("--since", help="Date de début UTC incluse : YYYY-MM-DD")
    parser.add_argument("--until", help="Date de fin UTC EXCLUE : YYYY-MM-DD")
    parser.add_argument("--all-available", action="store_true", help="Lire les blocs GetRecords disponibles et ignorer ceux d'horloge suspecte")
    args = parser.parse_args(argv)
    try:
        if args.command in ("export", "stats", "coverage"):
            db = connect(args.db)
            try:
                if args.command == "stats":
                    for name, value in stats(db).items():
                        print("{} : {}".format(name, value))
                elif args.command == "coverage":
                    coverage(db)
                else:
                    result = export_all(db, args.exports)
                    for name, count in result.items():
                        print("{} : {} lignes".format(name, count))
                    print("Fichiers CSV dans {}".format(args.exports))
            finally:
                db.close()
            return 0
        devices = load_devices(args.config)
        if args.device:
            devices = [d for d in devices if d["alias"] == args.device]
            if not devices:
                raise ValueError("Alias inconnu : {}".format(args.device))
        if args.command == "list":
            for d in devices:
                print("{:<16} {}  {}".format(d["alias"], d["host"], d.get("description", "")))
            return 0
        if args.command == "audit":
            return do_audit(devices, args.output)
        db = connect(args.db)
        try:
            if args.command == "daily":
                local_day = datetime.now().astimezone().date().isoformat()
                earlier = daily_outcome(db, local_day)
                if earlier is not None:
                    print("Collecte quotidienne {} déjà déclenchée ({}) ; pas de nouvelle lecture.".format(
                        local_day, earlier))
                    return 0
                # Évite de consommer la seule tentative du jour si le Mac n'est
                # pas sur le réseau RED : aucune lecture de donnée n'a lieu.
                import socket
                hosts = [device["host"] for device in devices]
                reachable = False
                for host in hosts:
                    try:
                        with socket.create_connection((host, 80), timeout=2):
                            reachable = True
                            break
                    except OSError:
                        pass
                if not reachable:
                    print("Réseau Shelly inaccessible : collecte non déclenchée.")
                    return 0
                if not claim_daily(db, local_day, current_utc()):
                    print("Collecte déjà en cours pour {}".format(local_day))
                    return 0
                outcome = False
                try:
                    outcome = run_collection(db, devices, args) == 0
                    return 0 if outcome else 1
                finally:
                    finish_daily(db, local_day, current_utc(), outcome)
            return run_collection(db, devices, args)
        finally:
            db.close()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("Erreur : {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
