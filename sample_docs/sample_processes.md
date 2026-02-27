# Betriebsprozesse und SLAs

## Service Level Agreements

### API-Gateway SLA
- **Verfügbarkeit:** 99,9% (≤ 8,7h Downtime/Jahr)
- **Latenz P99:** < 100ms (exkl. Backendlatenz)
- **Fehlerrate:** < 0,1% HTTP 5xx

### Auth Service SLA
- **Verfügbarkeit:** 99,95%
- **Token-Ausstellung:** < 50ms P99

## Deployment-Prozess

### Branching-Strategie
- `main` → Produktionsstand
- `develop` → Integrationsbranch
- `feature/*` → Feature-Branches (PR-basiert)
- Release via Git-Tags: `vMAJOR.MINOR.PATCH`

### CI/CD-Pipeline (GitHub Actions)

```yaml
stages:
  - lint (golangci-lint, hadolint)
  - test (Unit + Integration, >80% Coverage)
  - build (Docker Multi-Stage)
  - scan (Trivy Container Scan, OWASP Dependency Check)
  - deploy-staging (Helm Upgrade, Smoke Tests)
  - deploy-production (manuelles Approval-Gate)
```

### Rollback-Prozess
1. Identifiziere defekte Version via Grafana/PagerDuty
2. `helm rollback api-gateway -n production`
3. Verifiziere Health-Checks (30s Wartezeit)
4. Post-Mortem innerhalb 48h

## Backup & Recovery

### Datenbankbackups
- **Frequenz:** Täglich (23:00 UTC), stündliche WAL-Archivierung
- **Retention:** 30 Tage
- **Storage:** GCS Bucket (verschlüsselt, Versioning aktiviert)
- **Recovery Time Objective (RTO):** 4 Stunden
- **Recovery Point Objective (RPO):** 1 Stunde

### Recovery-Test
Monatlicher Recovery-Test auf Staging-Umgebung.
Dokumentation: `docs/recovery-test-{YYYY-MM}.md`

## Incident Management

### Schweregrade
| Level | Beschreibung | Reaktionszeit | Eskalation |
|-------|-------------|---------------|------------|
| P0    | Komplettausfall Produktion | 15min | CTO, alle TL |
| P1    | Kritische Funktion beeinträchtigt | 1h | TL on-call |
| P2    | Nicht-kritische Funktion beeinträchtigt | 4h | Team |
| P3    | Kosmetisch / Performance | Nächster Arbeitstag | Team |

### On-Call-Rotation
- Primär: Wochenschicht (Mo-So)
- Backup: Senior-Engineer der jeweiligen Woche
- Tool: PagerDuty

## Sicherheitsprozesse

### Vulnerability Management
- Wöchentlicher Trivy-Scan aller Container-Images
- OWASP Dependency Check in jeder CI-Pipeline
- CVEs mit CVSS ≥ 7.0: Patch innerhalb 7 Tage
- CVEs mit CVSS < 7.0: Patch im nächsten Sprint

### Access Management
- Least-Privilege-Prinzip für alle Service Accounts
- Quarterly Access Review (IAM-Audit)
- No-Shared-Secrets: Jeder Service hat eigene Credentials
- MFA-Pflicht für alle Produktionszugänge

## Änderungsmanagement

### Change Freeze
- Freitag 16:00 UTC bis Montag 08:00 UTC
- Ausnahmen: Security Hotfixes (P0/P1)

### Change Advisory Board (CAB)
- Wöchentlich Donnerstag 14:00 UTC
- Änderungen mit hohem Risiko benötigen CAB-Approval
