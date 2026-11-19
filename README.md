# Shelly Data Collector — Étape 3 : tout en local sur le Mac

**Aucun VPS, VPN ou cloud nécessaire.** Le Mac lit les Shelly du réseau RED, conserve les mesures dans `data/local.sqlite3`, génère les CSV et peut exécuter une collecte au maximum une fois par jour. Le code est compatible Python 3.8+ et n'utilise que la bibliothèque standard. **La programmation macOS n'est pas activée automatiquement.**

## Appareils configurés

- `em_gen3` — 192.168.1.60, EM Gen3, canaux 0/1, historique EM1Data.
- `chaudiere` — 192.168.1.58, Shelly 1 Gen4, photographie de son état (pas d'historique minute EM1Data).
- `em_gen4` — 192.168.1.41, EM Gen4, canaux 0/1, historique EM1Data.

Les IP figurent dans `config/devices.json` et doivent être ajustées si elles changent. **Les méthodes utilisées sont uniquement des lectures ; ce projet ne pilote pas les relais.**

## Installation dans le projet existant (important pour ne pas perdre 40 323 lignes)

1. Dans le Terminal **local du Mac**, se placer dans le projet : `cd ~/Documents/shelly`.
2. Vérifier qu'aucune collecte n'est en cours et effectuer une sauvegarde de la base **avant** la mise à jour :

   ```bash
   mkdir -p data/backups
   python3 - <<'PY'
   import sqlite3
   from pathlib import Path
   source = Path('data/local.sqlite3')
   if not source.is_file():
       raise SystemExit('Base locale introuvable : data/local.sqlite3')
   with sqlite3.connect(str(source)) as source_db, sqlite3.connect('data/backups/avant-etape3.sqlite3') as copy_db:
       source_db.backup(copy_db)
   print('Sauvegarde OK : data/backups/avant-etape3.sqlite3')
   PY
   ```

3. Décompresser l'archive du projet **par-dessus les fichiers du code existant** (`Makefile`, `src/`, `tests/`, `tools/`, `README.md`) **sans supprimer ni remplacer le dossier `data/`**. Ne pas exécuter de commande qui efface ou recrée la base. La configuration `config/devices.json` est fournie, à comparer avec la tienne si tu l'as modifiée.
4. Dans le Terminal :

   ```bash
   make test
   make stats
   make coverage
   make backup
   ```

   `make test`, `stats`, `coverage` et `backup` n'interrogent **aucun appareil**. Vérifier que `history_records` est au moins égal à 40 323 et que `daily_snapshots` est au moins égal à 3.

## Commandes utiles

| Commande | Rôle |
|---|---|
| `make list` | Inventaire local des appareils configurés |
| `make audit` | Diagnostic depuis le réseau local |
| `make stats` | Compter appareils, mesures, photographies, lancements journaliers |
| `make coverage` | Début, fin et discontinuités dans les mesures de chaque canal |
| `make backup` | Sauvegarde SQLite cohérente dans `data/backups/` |
| `make export` | Créer `data/exports/*.csv` depuis SQLite |
| `make daily` | Collecte incrémentale, au maximum un lancement planifié par jour local |
| `make collect DAYS=7` | Collecte manuelle d'une plage de 7 jours (à utiliser au besoin) |
| `make history DAYS=2` | Historique seulement, pour 2 jours glissants |
| `make backfill DEVICE=em_gen4` | Import de tous les blocs accessibles d'un compteur |
| `make schedule-show` | Voir la configuration `launchd` proposée, sans l'activer |
| `make schedule-install` | **Activer** `launchd`, uniquement après validation |
| `make schedule-remove` | **Désactiver** `launchd`, sans supprimer les données |

### `make daily` — comportement précis

- Ne lance aucune lecture si le réseau local Shelly est injoignable.
- Si la collecte a **déjà été déclenchée le même jour local**, n'interroge pas de nouveau les appareils, même si la première a échoué : c'est une protection stricte « 1 démarrage par jour ». Une collecte manuelle avec `make collect` reste possible en cas d'incident, mais n'est pas soumise à ce garde-fou.
- Pour chaque canal, reprend depuis la dernière minute locale enregistrée, avec un recouvrement de 2 heures pour corriger d'éventuelles valeurs. Si l'on n'a jamais importé d'historique, tente les 7 derniers jours.
- Rattrapage limité aux données que les appareils conservent encore. De plus anciens **trous au milieu de l'historique** demandent un `make backfill` manuel ; ce mode quotidien n'effectue pas une analyse exhaustive des lacunes.
- Ne réinvente pas d'états historiques du relais chaudière : pour lui, une photographie par jour où le Mac exécute le programme.
- Historique SQLite : clé primaire `(device_id, channel, timestamp_utc, period_s)` ; les mêmes données relues n'ajoutent pas de doublons.

> **Attention** : si le Mac reste éteint trop longtemps, certaines mesures peuvent être définitivement perdues car la mémoire des Shelly est limitée. Cette solution ne garantit pas 365 jours d'historique avec un Mac rarement allumé.

## Planification macOS — étape ultérieure facultative

La commande `make schedule-install` crée un LaunchAgent dans `~/Library/LaunchAgents/` avec un déclenchement **à l'ouverture de session** et **à 20:00** chaque jour (heure locale du Mac). Les deux déclenchements ne provoquent pas deux collectes le même jour grâce à la table `daily_runs`.

- **Mac éteint :** aucune collecte. Elle sera tentée lors de la prochaine ouverture de session.
- **Mac en veille :** le déclenchement calendrier peut être reporté au réveil selon macOS.
- **Mac utilisé hors du réseau RED :** aucune collecte ne démarre ; relancer `make daily` en rentrant chez soi si nécessaire.
- Logs : `data/logs/daily.log` et `data/logs/daily.error.log`.
- Désinstallation : `make schedule-remove`.

`launchd` n'a pas besoin de VPN, de port ouvert sur le routeur ni d'accès VPS. Pour des mesures garanties chaque jour malgré l'arrêt du Mac, un appareil local toujours allumé serait nécessaire.

## Protection des données et évolution vers VPS

`data/` est exclu de Git par `.gitignore` : ne le publier ni sur GitHub ni ailleurs. Conserver des sauvegardes sur un disque distinct si les historiques sont importants. `make backup` enregistre une sauvegarde **sur le même Mac** : cela ne protège pas d'une panne du disque.

Le code sépare `history.py` (lecture), `storage.py` (stockage SQLite), `exporters.py` (CSV) et `cli.py` (orchestration). Un éventuel export/synchronisation vers VPS pourrait être ajouté plus tard comme module optionnel : **aucun transfert n'est programmé aujourd'hui**.

## Documentation

- https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EM1Data/
- https://shelly-api-docs.shelly.cloud/gen2/Devices/Gen4/ShellyEMG4/
