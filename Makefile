# Étape 1 : diagnostic lecture seule (Mac, Python >= 3.8, sans dépendance externe)
PYTHON ?= python3
PYTHONPATH := src
export PYTHONPATH
.PHONY: help list audit test
help:
	@echo "make list   : affiche les appareils configurés (sans accès réseau)"
	@echo "make audit  : diagnostic réseau + métadonnées des historiques (LECTURE SEULE)"
	@echo "make test   : tests unitaires sans appareil Shelly"
list:
	$(PYTHON) -m shelly_collector.cli list
audit:
	$(PYTHON) -m shelly_collector.cli audit
test:
	$(PYTHON) -m unittest discover -s tests -v
