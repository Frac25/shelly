# Étape 3 : tout est LOCAL sur le Mac, aucune dépendance VPS.
PYTHON ?= python3
PYTHONPATH := src
export PYTHONPATH
DAYS ?= 7
DEVICE ?=
SINCE ?=
UNTIL ?=
FLAGS = $(if $(DEVICE),--device $(DEVICE),) $(if $(SINCE),--since $(SINCE),) $(if $(UNTIL),--until $(UNTIL),)
.PHONY: help list audit test snapshot history collect daily backfill export stats coverage backup schedule-show schedule-install schedule-remove
help:
	@echo "make test                         Tests sans appareil"
	@echo "make list                         Inventaire configuré"
	@echo "make audit                        Diagnostic des appareils"
	@echo "make collect DAYS=7              Lecture ponctuelle (snapshot + historique)"
	@echo "make daily                        Collecte incrementale, maximum 1 déclenchement/jour"
	@echo "make history DAYS=3               Historique 3 derniers jours, sans snapshot"
	@echo "make backfill                     Tous les blocs historiques accessibles"
	@echo "make coverage                     Début/fin et trous chronologiques par canal"
	@echo "make stats                        Statistiques de la base locale"
	@echo "make export                       Exports CSV pour Excel"
	@echo "make backup                       Sauvegarde cohérente de SQLite"
	@echo "make schedule-show                Voir la programmation launchd proposée"
	@echo "make schedule-install             ACTIVER la tâche quotidienne sur ce Mac"
	@echo "make schedule-remove              DÉSACTIVER la tâche quotidienne"
list:
	$(PYTHON) -m shelly_collector.cli list
audit:
	$(PYTHON) -m shelly_collector.cli audit
snapshot:
	$(PYTHON) -m shelly_collector.cli snapshot $(FLAGS)
history:
	$(PYTHON) -m shelly_collector.cli history --days $(DAYS) $(FLAGS)
collect:
	$(PYTHON) -m shelly_collector.cli collect --days $(DAYS) $(FLAGS)
daily:
	$(PYTHON) -m shelly_collector.cli daily
backfill:
	$(PYTHON) -m shelly_collector.cli history --all-available $(if $(DEVICE),--device $(DEVICE),)
export:
	$(PYTHON) -m shelly_collector.cli export
stats:
	$(PYTHON) -m shelly_collector.cli stats
coverage:
	$(PYTHON) -m shelly_collector.cli coverage
backup:
	$(PYTHON) -m shelly_collector.backup
schedule-show:
	$(PYTHON) tools/launchd_manager.py show
schedule-install:
	$(PYTHON) tools/launchd_manager.py install
schedule-remove:
	$(PYTHON) tools/launchd_manager.py remove
test:
	$(PYTHON) -m unittest discover -s tests -v
