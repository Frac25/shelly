# Etape 2 : lecture manuelle, base SQLite LOCALE, aucun cron/launchd.
PYTHON ?= python3
PYTHONPATH := src
export PYTHONPATH
DAYS ?= 7
DEVICE ?=
SINCE ?=
UNTIL ?=
FLAGS = $(if $(DEVICE),--device $(DEVICE),) $(if $(SINCE),--since $(SINCE),) $(if $(UNTIL),--until $(UNTIL),)
.PHONY: help list audit test snapshot history collect backfill export stats
help:
	@echo "make list                          Inventaire"
	@echo "make audit                         Diagnostic précédent"
	@echo "make snapshot                      Un état par appareil/jour"
	@echo "make history DAYS=7                Historique glissant"
	@echo "make history DEVICE=em_gen3 DAYS=1 Test sur 1 seul compteur"
	@echo "make backfill                      Tous les blocs historiques accessibles"
	@echo "make collect DAYS=7                Snapshot + historique"
	@echo "make export                        CSV pour Excel"
	@echo "make stats                         Nombre de mesures stockées"
	@echo "make test                          Tests sans appareils"
list:
	$(PYTHON) -m shelly_collector.cli list

# audit, aucune écriture Shelly
audit:
	$(PYTHON) -m shelly_collector.cli audit
snapshot:
	$(PYTHON) -m shelly_collector.cli snapshot $(FLAGS)
history:
	$(PYTHON) -m shelly_collector.cli history --days $(DAYS) $(FLAGS)
collect:
	$(PYTHON) -m shelly_collector.cli collect --days $(DAYS) $(FLAGS)
backfill:
	$(PYTHON) -m shelly_collector.cli history --all-available $(if $(DEVICE),--device $(DEVICE),)
export:
	$(PYTHON) -m shelly_collector.cli export
stats:
	$(PYTHON) -m shelly_collector.cli stats
test:
	$(PYTHON) -m unittest discover -s tests -v
