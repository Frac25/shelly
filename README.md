# Shelly Data Collector — Étape 1 : diagnostic Mac

Projet de diagnostic **en lecture seule** pour 3 appareils Shelly du réseau RED.
Aucun service n'est installé, aucune tâche quotidienne n'est programmée, aucun relais n'est modifié.

## Compatibilité
- Mac Intel sous macOS 10.15.8 (Catalina)
- Fonctionne au stade diagnostic avec Python **3.8.5** déjà présent, car uniquement bibliothèque standard
- Objectif à terme : Python récent, stockage SQLite sur VPS Debian 12, synchronisation SSH

## Lancer dans VS Code (terminal LOCAL du Mac)

```bash
cd ~/Documents/shelly
python3 --version
make list
make test
make audit
```

Le dernier appel interroge chaque appareil une seule fois pour `/shelly`,
une fois pour `/rpc/Shelly.GetStatus`, puis la **première page**
des intervalles historiques via `EM1Data.GetRecords` pour les compteurs.
Il n'effectue **pas** encore de téléchargement complet des mesures.

Résultat : `data/diagnostic.json`. Le fichier contient le modèle, les composants,
les plages d'historique visibles et les erreurs éventuelles, mais pas la réponse
complète de statut ni les informations réseau Wi-Fi sensibles.

## Préparer le dossier

Télécharge et décompresse cette archive dans un dossier temporaire. Copie son
contenu dans `~/Documents/shelly`. **Ne remplace pas** des fichiers existants sans
vérifier : ce dossier peut déjà contenir tes propres modifications.

## Fichiers
- `config/devices.json` : tes 3 IP/alias initiaux. Éditable.
- `src/shelly_collector/http.py` : GET strictement limité aux 3 endpoints de lecture.
- `src/shelly_collector/diagnostic.py` : résumé des métadonnées.
- `src/shelly_collector/cli.py` : interface de commande.
- `tests` : tests sans réseau.
- `data` : fichiers locaux ignorés par Git.

## Limites volontaires de l'étape 1
- Pas de collecte automatisée ni de synchronisation vers le VPS.
- Pas d'export CSV ni de base SQLite : étapes suivantes après validation.
- Une page de `GetRecords` ne prouve pas la totalité de l'historique :
  l'import final gérera la pagination et les horodatages.
- Une tâche quotidienne peut récupérer un historique à la minute *si* celui-ci
  est conservé par les compteurs. Pour le relais de chaudière, les basculements
  intermédiaires non enregistrés ne sont pas reconstituables.

## Sécurité
N'ouvre pas les ports des Shelly sur Internet. Aucune connexion entrante n'est
nécessaire depuis le VPS. Les identifiants d'appareils et les mots de passe ne sont
pas nécessaires pour les 3 appareils testés (`auth_en: false`), mais active une
protection réseau domestique adaptée, car une API locale non authentifiée peut
être pilotée par des appareils déjà présents sur ton LAN.

## Documentation
- https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EM1Data/
- https://shelly-api-docs.shelly.cloud/gen2/Devices/Gen4/ShellyEMG4/
- https://www.shelly.com/blogs/documentation/shelly-em-gen3
