# Systemarchitektur: API-Gateway-Migration

## Übersicht

Das Projekt migriert die bestehende monolithische Backend-Anwendung zu einer
Microservice-Architektur. Zentrales Element ist ein API-Gateway (Kong), das
alle eingehenden Anfragen routet, authentifiziert und rate-limitiert.

## Komponenten

### 1. API-Gateway (Kong)

Kong wird als zentraler Einstiegspunkt für alle Client-Anfragen eingesetzt.
Konfiguration erfolgt deklarativ via Kong Deck (GitOps-Ansatz).

Plugins aktiviert:
- `jwt` – JWT-basierte Authentifizierung
- `rate-limiting` – 1000 Req/min pro API-Key
- `prometheus` – Metriken-Exposition für Grafana
- `request-transformer` – Header-Manipulation für Legacy-Kompatibilität

### 2. Auth Service

Verantwortlich für:
- Ausstellung und Validierung von JWT-Tokens (RS256)
- RBAC (Role-Based Access Control) mit PostgreSQL als Backend
- Refresh-Token-Rotation mit 7-Tage-TTL

Technologien: Go 1.21, JWT-go, PostgreSQL 15, Redis (Token-Blacklisting)

### 3. User Service

REST-API für Benutzerverwaltung:
- CRUD-Operationen auf Benutzerdaten
- Soft-Delete-Muster (Datenschutzkonformität)
- GDPR-Export-Endpoint (`GET /users/{id}/export`)

Datenbank: PostgreSQL 15 mit Row-Level Security (RLS)

### 4. Notification Service

Asynchrone Event-basierte Benachrichtigungen:
- Kafka als Message Broker (3 Broker, Replikationsfaktor 3)
- Unterstützte Kanäle: E-Mail (SendGrid), Push (FCM), SMS (Twilio)
- Dead-Letter-Queue für fehlgeschlagene Zustellungen

### 5. API-Gateway-seitige Authentifizierung

Alle Services validieren JWTs nicht eigenständig – die Validierung erfolgt
ausschließlich am Gateway. Services kommunizieren intern via mTLS.

## Infrastruktur

Deployment auf Kubernetes (GKE):
- 3 Worker-Nodes (n2-standard-4)
- Namespace-Isolation pro Service
- Network Policies: deny-all default, selektives Whitelisting
- Secrets Management: HashiCorp Vault

## Datenfluss (vereinfacht)

```
Client → Kong API-Gateway → [Auth Plugin: JWT validieren]
       → Route zu Service → Service Business Logic
       → Response ← Service
       ← Kong (Rate-Limit-Header hinzufügen) ← Client
```

## Entscheidungen

### ADR-001: Kong statt AWS API Gateway

**Kontext:** Wir benötigen ein API-Gateway, das On-Premise und Cloud betreibbar ist.

**Entscheidung:** Kong (Community Edition) wird eingesetzt.

**Begründung:**
- Vendor-Unabhängigkeit (kein Cloud-Lock-in)
- Umfangreiche Plugin-Bibliothek
- Declarative Configuration via Deck

**Alternativen:** AWS API Gateway (abgelehnt: Cloud-Lock-in), Traefik (abgelehnt: eingeschränkte Plugin-Unterstützung)

### ADR-002: JWT mit RS256 statt HS256

**Entscheidung:** Asymmetrische Signaturverfahren (RS256) für JWTs.

**Begründung:** Services können ohne Kenntnis des privaten Schlüssels Tokens
verifizieren. Reduziert das Risiko bei Key-Kompromittierung.

## Betrieb

### Deployment

```bash
# Staging
kubectl apply -f k8s/staging/ -n api-gateway-staging

# Production (via CI/CD)
# Trigger: Git-Tag mit Pattern vX.Y.Z
# Pipeline: GitHub Actions → Docker Build → GCR Push → Helm Upgrade
```

### Monitoring

- Grafana Dashboards: `dashboards/api-gateway.json`
- Alerts: PagerDuty bei P50 > 200ms, P99 > 1s, Error-Rate > 1%
- Logs: Loki + Promtail (strukturiert, JSON)

### Runbook: Gateway nicht erreichbar

1. Prüfe Kong-Pod-Status: `kubectl get pods -n api-gateway`
2. Logs: `kubectl logs -n api-gateway -l app=kong --tail=100`
3. Prüfe Datenbank-Verbindung (Kong benötigt PostgreSQL)
4. Fallback: Direktrouting via Service-Mesh (Istio-Bypass)
5. Eskalation: Platform-Team Slack #oncall

## Risiken

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| Kong-PostgreSQL-Verbindungsausfall | Mittel | Hoch | Retry-Logik, Connection Pooling (PgBouncer) |
| JWT-Key-Kompromittierung | Niedrig | Kritisch | Key-Rotation-Prozess, Vault-Integration |
| Kafka-Partition-Leader-Ausfall | Niedrig | Mittel | min.insync.replicas=2, acks=all |
| DDoS auf API-Gateway | Mittel | Hoch | Cloudflare WAF vorgelagert, Rate Limiting |

## Glossar

- **API-Gateway**: Zentraler Einstiegspunkt für API-Anfragen
- **JWT**: JSON Web Token – kompaktes, URL-sicheres Token-Format
- **mTLS**: Mutual TLS – gegenseitige Zertifikatsauthentifizierung
- **RLS**: Row-Level Security – datenbankgestützte Zugriffskontrolle auf Zeilenebene
- **DLQ**: Dead-Letter-Queue – Warteschlange für nicht zustellbare Nachrichten
