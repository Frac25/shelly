# Shelly Data Collector — Étape 2 (Mac)

**Projet sans dépendance externe, compatible Python 3.8.5.** Il ne modifie jamais les appareils, ne pilote jamais les relais, et n'installe **aucune** tâche quotidienne. La base SQLite de cette étape est **locale sur le Mac** : le stockage central sur le VPS arrivera à l'étape 3.

## Installation dans le projet existant

1. Faire une copie du dossier `~/Documents/shelly` actuel, ou un commit Git.
2. Décompresser l'archive, copier ses fichiers dans `~/Documents/shelly` (conserver le dossier `data/` déjà présent).
3. Lancer dans le terminal **local** du Mac :

```bash
cd ~/Documents/shelly
make test
make list
make history DEVICE=em_gen3 DAYS=1
make stats
make export
```

**Le premier essai ne lit qu'un compteur sur les dernières 24 heures.** Quand c'est validé :

```bash
make collect DAYS=7
make stats
make export
```

Les quatre historiques (Gen3 et Gen4, canaux 0 et 1) seront alors importés; le relais chaudière aura une photographie de son état courant. Les données sont conservées dans `data/local.sqlite3`; les exports CSV sont dans `data/exports/`.

## Autres commandes

```bash
make audit
make snapshot                 # une photo par jour civil et appareil
make history DAYS=3           # les 3 derniers jours, pas de photo
make history SINCE=2026-11-12 UNTIL=2026-11-20 # UTC, borne de fin exclue
make backfill                 # toutes les plages annoncées par GetRecords
make backfill DEVICE=em_gen4  # uniquement le Gen4
make stats
make export
```

`make backfill` peut demander de nombreuses requêtes (une heure par fenêtre) et prendra plus de temps. Il n'efface rien et peut être relancé. Les blocs dont l'horodatage est incohérent (antérieur à 2020 ou futur) sont enregistrés en métadonnées dans `suspect_blocks` et exclus du CSV principal. Leur contenu sur l'appareil n'est jamais effacé. Dans cet état, l'enregistrement des données de ces blocs est **différé** jusqu'à validation de l'horloge et de leur correspondance réelle.

### Déduplication

- Identifiant stable Shelly `id` (non IP ou alias), canal, timestamp UNIX UTC, période : clé primaire dans `history`.
- Une mesure corrigée par le Shelly est mise à jour; une mesure identique ne change pas.
- Les snapshots `Shelly.GetStatus` sont limités à un **par jour civil selon la zone locale du Mac**, et par appareil. Une journée où le Mac est éteint ne crée pas de fausse photo.
- Les CSV sont régénérés à partir de la base, pas accumulés fichier après fichier.
- En cas d'échec réseau, la prochaine commande relance la même période sans doublons; pour les trous historiques, utiliser `make backfill` ou `SINCE/UNTIL`.

### Contraintes / vigilance

- Les mesures qui n'ont jamais été enregistrées dans l'appareil (notamment les basculements passés du relais) ne sont pas récupérables par cette API.
- Si les appareils ont des mesures plus anciennes que 7 jours, utiliser `make backfill`; celui-ci vérifie les blocs `EM1Data.GetRecords`, la page n°1 du diagnostic ne suffit pas.
- L'import sur Mac ne prouve pas encore que toutes les réponses de firmware réel respectent les exemples de la documentation officielle. Si une erreur de format survient, interrompre et transmettre **le message d'erreur**, sans clés API ni mots de passe. On adaptera le décodeur.
- L'export des états peut contenir des noms de réseau, IP et autres métadonnées : garder `data/` privé, ne pas publier sous Git.
- `data/local.sqlite3`, ses éventuels fichiers WAL et les exports doivent être sauvegardés avant toute réinstallation.

## Documents officiels

- https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EM1Data/
- https://shelly-api-docs.shelly.cloud/gen2/Devices/Gen4/ShellyEMG4/
