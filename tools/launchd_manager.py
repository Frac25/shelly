"""Installer/désinstaller volontairement la tâche locale macOS."""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "fr.local.shelly.collector.daily"
ROOT = Path(__file__).resolve().parents[1]
PLIST = Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")


def launchd_definition(root=ROOT, python=None):
    root = Path(root).resolve()
    exe = str(Path(python or sys.executable).resolve())
    data = root / "data"
    return {
        "Label": LABEL,
        "ProgramArguments": [exe, "-m", "shelly_collector.cli", "daily"],
        "WorkingDirectory": str(root),
        "EnvironmentVariables": {"PYTHONPATH": str(root / "src")},
        "RunAtLoad": True,
        "StartCalendarInterval": {"Hour": 20, "Minute": 0},
        "StandardOutPath": str(data / "logs" / "daily.log"),
        "StandardErrorPath": str(data / "logs" / "daily.error.log"),
    }


def main():
    if sys.platform != "darwin":
        raise SystemExit("Cette commande nécessite macOS (Darwin).")
    if len(sys.argv) != 2 or sys.argv[1] not in ("install", "remove", "show"):
        raise SystemExit("Usage : launchd_manager.py install|remove|show")
    action = sys.argv[1]
    if action == "show":
        print(plistlib.dumps(launchd_definition()).decode("utf-8"))
        return
    if action == "install":
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        (ROOT / "data" / "logs").mkdir(parents=True, exist_ok=True)
        if PLIST.exists():
            subprocess.run(["launchctl", "unload", "-w", str(PLIST)], check=False)
        with PLIST.open("wb") as fh:
            plistlib.dump(launchd_definition(), fh)
        print("Activation de la tâche : lancement à la connexion et à 20h si disponible.")
        subprocess.run(["launchctl", "load", "-w", str(PLIST)], check=True)
        print("Tâche installée : {}".format(PLIST))
    elif PLIST.exists():
        subprocess.run(["launchctl", "unload", "-w", str(PLIST)], check=False)
        PLIST.unlink()
        print("Planification retirée ; aucune donnée locale supprimée.")
    else:
        print("Aucune tâche installée.")


if __name__ == "__main__":
    main()
