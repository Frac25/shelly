"""CLI étape 1. Aucune programmation et aucune action sur les relais."""
import argparse
import json
import pathlib
import sys

from .diagnostic import current_utc, diagnostic_device
from .http import validate_local_host

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "devices.json"
DEFAULT_OUTPUT = ROOT / "data" / "diagnostic.json"


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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Diagnostic Shelly en lecture seule (Mac)")
    parser.add_argument("command", choices=("list", "audit"), help="list=configuration; audit=HTTP local et métadonnées historiques")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Chemin vers devices.json")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Fichier JSON de diagnostic")
    args = parser.parse_args(argv)
    try:
        devices = load_devices(args.config)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("Erreur configuration : {}".format(exc), file=sys.stderr)
        return 2

    if args.command == "list":
        for item in devices:
            print("{:<16} {}  {}".format(item["alias"], item["host"], item.get("description", "")))
        return 0

    report = {"diagnostic_utc": current_utc(), "mode": "read_only", "devices": []}
    failed = 0
    for item in devices:
        print("\n--- {} ({}) ---".format(item["alias"], item["host"]))
        result = diagnostic_device(item)
        report["devices"].append(result)
        identity = result["identity"] or {}
        print("Modèle : {} | Gen {} | Firmware {}".format(identity.get("model", "non identifié"), identity.get("gen", "?"), identity.get("ver", "?")))
        print("Composants : {}".format(", ".join(result["components"]) or "non disponibles"))
        for label, summary in sorted(result["history"].items()):
            if "error" in summary:
                print("Historique {} : erreur : {}".format(label, summary["error"]))
            else:
                print("Historique {} : {} bloc(s) visibles, période(s) {} s, du {} au {} (UTC)".format(
                    label, summary["data_blocks_on_page"], summary["periods_seconds_on_page"],
                    summary["first_timestamp_utc_on_page"], summary["last_timestamp_utc_on_page"]))
        for error in result["errors"]:
            print("ATTENTION : {}".format(error))
        if result["errors"] or any("error" in entry for entry in result["history"].values()):
            failed += 1

    target = pathlib.Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\nDiagnostic enregistré dans {}".format(target))
    if failed:
        print("Attention : {} appareil(s) avec une ou plusieurs erreurs".format(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
