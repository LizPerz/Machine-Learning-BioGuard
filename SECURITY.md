# Security Policy — BioGuard ML Service

## Modelo de seguridad (DevSecOps)

BioGuard es un microservicio de inferencia clínica. La seguridad se aplica como
código en cada capa:

| Capa | Herramienta | Qué detecta |
|---|---|---|
| Commit / PR | pre-commit (ruff, bandit, gitleaks) | Secretos, SAST, estilo |
| CI | Gitleaks | Fugas de secretos en el repo |
| CI | Bandit + Semgrep + CodeQL | Vulnerabilidades en el código (SAST) |
| CI | pip-audit | CVEs en dependencias (SCA) |
| CI | Syft/Anchore | SBOM (inventario de componentes) |
| CI | Trivy | CVEs en imagen Docker + misconfig de IaC |
| CI | OWASP ZAP | Vulnerabilidades dinámicas (DAST) |
| CI | Checkov | Políticas de IaC (Dockerfile) |
| CI | Dependency Review | Bloqueo de CVEs en PRs |
| CI | Cosign (keyless OIDC) | Firma de imagen / SLSA (supply chain) |
| Runtime | JWT servicio-a-servicio + cabeceras OWASP + rate limiting | Autenticación y endurecimiento HTTP |

## Versiones soportadas

| Versión | Soportada |
|---|---|
| 2.x (main) | ✅ |

## Cifrado y secretos

- El `BIOGUARD_SERVICE_TOKEN_SECRET` debe tener ≥ 32 caracteres, generado con un
  CSPRNG (p. ej. `python -c "import secrets;print(secrets.token_urlsafe(32))"`).
- Nunca se commitea un `.env` real (ver `.gitignore` / `.dockerignore`).
- El JWT usa HS256 con `iss`/`aud` fijos y expiración corta; se exige `exp`/`iat`.

## Cómo reportar una vulnerabilidad

**No** abras un issue público para vulnerabilidades.

Envía el reporte a `security@bioguard.app` (PGP opcional) con:

1. Descripción y impacto.
2. Pasos de reproducción / PoC.
3. Versión afectada.
4. Sugerencia de mitigación (si la tienes).

Nos comprometemos a acusar recibo en 72h y a proporcionar un plan de
remediación en 15 días para incidencias críticas.

## Hardening del despliegue

- Imagen Docker multi-etapa, usuario no-root (UID 10001), HEALTHCHECK configurado.
- Cabeceras OWASP inyectadas en cada respuesta (HSTS, CSP, X-Frame-Options…).
- Rate limiting por IP en producción; límite de payload de 2 MB para mitigar DoS.
- Validación estricta de entrada (`extra="forbid"`) para evitar campos no
  contractados.

## Cadena de suministro (Supply Chain / SLSA)

- La imagen se construye de forma reproducible y se publica en GHCR.
- Se firma con **Cosign** usando identidad keyless (OIDC de GitHub Actions),
  cumpliendo los principios SLSA. Verifica la firma antes de desplegar:

  ```bash
  cosign verify ghcr.io/<org>/<repo>@<digest> \
    --certificate-identity-regexp 'https://github.com/<org>/<repo>/.github/workflows/ci.yml@.*' \
    --certificate-oidc-issuer 'https://token.actions.githubusercontent.com'
  ```

- `CODEOWNERS` exige revisión humana de cualquier cambio en `app/` y en la
  configuración de seguridad antes de merge.
- `DEPENDABOT` + `dependency-review` actualizan y bloquean dependencias con CVEs.
