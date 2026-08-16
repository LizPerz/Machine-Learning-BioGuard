# BioGuard ML — Objetivos DevSecOps locales (shift-left)
# Uso: make <objetivo>

PYTHON ?= python
PIP    ?= $(PYTHON) -m pip

.PHONY: help install devsecops-install lint sast secret-scan sca iac sbom test precommit ci-local

help:
	@echo "Objetivos DevSecOps disponibles:"
	@echo "  install          Instala dependencias de producción + dev"
	@echo "  devsecops-install Instala herramientas de seguridad locales"
	@echo "  lint             Ruff (lint + format check)"
	@echo "  sast             Bandit sobre app/"
	@echo "  secret-scan      Gitleaks sobre el repo"
	@echo "  sca              pip-audit + safety (CVEs en dependencias)"
	@echo "  iac              Checkov (políticas de IaC/Dockerfile)"
	@echo "  sbom             Genera SBOM (CycloneDX) localmente"
	@echo "  test             pytest + cobertura"
	@echo "  precommit        Ejecuta todos los hooks de pre-commit"
	@echo "  ci-local         Equivalente local de la pipeline DevSecOps"

install:
	$(PIP) install -r requirements.txt -r requirements-dev.txt

devsecops-install:
	$(PIP) install ruff bandit pip-audit pip-licenses pre-commit safety checkov
	@command -v gitleaks >/dev/null 2>&1 || echo "Instala gitleaks manualmente: https://github.com/gitleaks/gitleaks"

lint:
	ruff check app tests

sast:
	bandit -r app -ll -ii -c bandit.yaml

secret-scan:
	gitleaks detect --source . --config .gitleaks.toml --redact

sca:
	pip-audit -r requirements.txt
	safety check -r requirements.txt

iac:
	checkov -d . --framework dockerfile --quiet

sbom:
	$(PIP) install cyclonedx-bom
	cyclonedx-py -r requirements.txt -o sbom.json

test:
	$(PYTHON) -m pytest --cov=app --cov-report=term-missing --cov-fail-under=80

precommit:
	pre-commit run --all-files

ci-local: lint sast secret-scan sca iac test
	@echo "Pipeline DevSecOps local completada."
