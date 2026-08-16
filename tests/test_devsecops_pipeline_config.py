"""Pruebas de cumplimiento DevSecOps a nivel de configuración del proyecto.

Valida que la infraestructura de seguridad (Dockerfile endurecido, escaneo de
secretos, pre-commit, CI con todas las fases DevSecOps, .gitignore/.dockerignore
que excluyen `.env`, .env.example sin secretos reales, Dependabot) esté
presente y correctamente configurada. No ejecuta la aplicación.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _leer(ruta: pathlib.Path) -> str:
    return ruta.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile endurecido (non-root + healthcheck + sin ADD inseguro)
# ─────────────────────────────────────────────────────────────────────────────


def test_dockerfile_usa_usuario_no_root():
    texto = _leer(ROOT / "Dockerfile")
    assert re.search(r"^USER\s+\d+", texto, re.M), "El Dockerfile debe usar un USER no-root (UID)"


def test_dockerfile_tiene_healthcheck():
    texto = _leer(ROOT / "Dockerfile")
    assert "HEALTHCHECK" in texto, "El Dockerfile debe definir un HEALTHCHECK"


def test_dockerfile_no_usa_latest_tag():
    texto = _leer(ROOT / "Dockerfile")
    assert "latest" not in texto, "Evitar tags 'latest' no reproducibles en el Dockerfile"


# ─────────────────────────────────────────────────────────────────────────────
# Archivos de configuración DevSecOps presentes
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ruta",
    [
        ".gitleaks.toml",
        ".pre-commit-config.yaml",
        ".trivyignore",
        ".checkov.yaml",
        "bandit.yaml",
        ".github/dependabot.yml",
        ".github/CODEOWNERS",
        ".github/codeql/codeql-config.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/dependency-review.yml",
    ],
)
def test_archivos_devsecops_existen(ruta):
    assert (ROOT / ruta).exists(), f"Falta el archivo DevSecOps: {ruta}"


def test_codeowners_exige_revision():
    texto = _leer(ROOT / ".github" / "CODEOWNERS")
    assert "@" in texto, "CODEOWNERS debe asignar revisores"
    assert "/app/" in texto, "Los cambios en app/ deben requerir revisión"


def test_dependency_review_workflow_existe():
    texto = _leer(ROOT / ".github" / "workflows" / "dependency-review.yml").lower()
    assert "dependency-review-action" in texto
    assert "fail-on-severity" in texto


# ─────────────────────────────────────────────────────────────────────────────
# CI contiene todas las fases DevSecOps
# ─────────────────────────────────────────────────────────────────────────────


def test_ci_incluye_fases_devsecops():
    ci = _leer(ROOT / ".github" / "workflows" / "ci.yml").lower()
    fases = {
        "gitleaks": "secret scanning",
        "bandit": "SAST",
        "semgrep": "SAST",
        "pip-audit": "SCA",
        "safety": "segundo motor SCA",
        "sbom": "SBOM",
        "trivy": "container/IaC scan",
        "checkov": "IaC policy scan",
        "cosign": "firma de imagen (SLSA)",
        "zap": "DAST",
        "codeql": "deep code analysis",
        "security-gate": "puerta de seguridad agregada",
    }
    for herramienta, descripcion in fases.items():
        assert herramienta in ci, f"La CI debe incluir {descripcion} ({herramienta})"


def test_ci_usa_concurrencia_y_permissions():
    ci = _leer(ROOT / ".github" / "workflows" / "ci.yml")
    assert "concurrency:" in ci, "El workflow debe evitar ejecuciones duplicadas"
    assert "id-token: write" in ci, "Se requiere OIDC (id-token) para firma SLSA/cosign"


def test_ci_usa_permisos_minimos():
    ci = _leer(ROOT / ".github" / "workflows" / "ci.yml")
    assert "permissions:" in ci, "El workflow debe declarar permissions mínimos"
    # No debe pedir permiso de escritura sobre contenidos en el workflow principal.
    assert "contents: read" in ci, "El token debe tener contents: read (mínimo privilegio)"


# ─────────────────────────────────────────────────────────────────────────────
# Gestión de secretos: .env nunca se versiona; .env.example solo placeholders
# ─────────────────────────────────────────────────────────────────────────────


def test_gitignore_excluye_env():
    texto = _leer(ROOT / ".gitignore")
    assert ".env" in texto, ".gitignore debe excluir .env"


def test_dockerignore_excluye_env():
    texto = _leer(ROOT / ".dockerignore")
    assert ".env" in texto, ".dockerignore debe excluir .env"


def test_env_example_sin_secretos_reales():
    texto = _leer(ROOT / ".env.example")
    lineas = texto.splitlines()
    for linea in lineas:
        if linea.startswith("BIOGUARD_SERVICE_TOKEN_SECRET"):
            assert "<" in linea and ">" in linea, (
                "El secreto en .env.example debe ser un placeholder, no un valor real"
            )
        if linea.startswith("BIOGUARD_MONGO_URI"):
            assert "<" in linea and ">" in linea, (
                "La URI de Mongo en .env.example debe ser un placeholder"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Dependencias: versionadas y con herramientas de escaneo en dev
# ─────────────────────────────────────────────────────────────────────────────


def test_requirements_usan_rangos_acotados():
    texto = _leer(ROOT / "requirements.txt")
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or linea.startswith("-"):
            continue
        # Debe tener un operador de versión (>=, ==, ~=, <=) para evitar drift.
        assert re.search(r"[><=~]=", linea), f"Dependencia sin versión acotada: {linea}"


def test_requirements_dev_incluye_herramientas_seguridad():
    texto = _leer(ROOT / "requirements-dev.txt").lower()
    for herr in ("pytest", "ruff", "bandit", "pip-audit"):
        assert herr in texto, f"requirements-dev.txt debe incluir {herr}"
