# Wiederherstellung aus diesem Git-Repository

**Nur öffentliche Betriebsvorlagen — keine Anmeldeinformationen.** Alle Passwörter, Teacher-Token, Tunnel-Zugangscodes und Unterrichtsdaten müssen privat beigestellt werden. Sie sind **nicht** in diesem Repository enthalten und auch nicht über den Handoff rekonstruierbar.

## Voraussetzungen (beide Rechner)

| Komponente | Anforderung |
|------------|-------------|
| Git + GitHub CLI | `gh` angemeldet, Leserecht auf `igathedub/pod-racing-classroom` |
| Docker Desktop / Colima | Linux-Container aktiv, **dedizierter** Kontext (nicht der Produktiv-Daemon) |
| Python 3.11 + `uv` | Testablauf; keine Produktionsexekution nötig |
| Cloudflare-Account | Nur für den primären/reellen Tunnel. Der Reserve-Rechner braucht eine eigene Tunnel-UUID. |

## Schritt-für-Schritt: neuer Rechner aus Git wiederherstellen

```bash
# 1. Frischer Klon + Branch checkout (oder merged main)
git clone https://github.com/igathedup/pod-racing-classroom.git
cd pod-racing-classroom
git switch feat/mac-backup-base-path   # bzw. main nach dem Merge

# 2. Python-Test-Umgebung
uv sync --frozen --python 3.11
uv run playwright install chromium
uv run pytest -m "not docker"          # 256 tests (30 Docker-geskippt)

# 3. Private Operator-Secretdatei erstellen
cp deploy/operator.env.example ~/private/pod-classroom.env
chmod 600 ~/private/pod-classroom.env
```

In `~/private/pod-classroom.env` müssen **existierende** Werte eingetragen werden:

| Variable | Rolle | Beispiel / Herkunft |
|----------|-------|---------------------|
| `POD_SITE_USER` | Website-Benutzername beider Gateways | `igor` (oder der bestehende) |
| `POD_SITE_PASSWORD_HASH` | argon2id-Hash des Website-Passworts | Windows-Hermes Vault oder bestehender `.env` auf dem Primärserver |
| `POD_APP_IMAGE` | Exakter, unveränderlicher App-Image-Tag | z.B. `pod-classroom-release:sha256:<digest>` (von Docker Image Inspect) |
| `POD_BOT_IMAGE` | Bot/Sandbox-Image | Gleicher oder eigener lokaler Build-Tag |
| `POD_DATA_VOLUME` | Name des **existierenden** Classroom-Volumes | vom Backup-Manifest oder `docker volume ls` |
| `POD_DOCKER_SOCKET` | Unix-Socket-Pfad | `/var/run/docker.sock` (Linux / Colima) bzw. Docker-Desktop Socket |
| `POD_BACKUP_EDGE_SECRET` | Nur Reserve-Rolle: Marker für Cloudflare Worker | Gleicher Wert wie in der Cloudflare Worker Secret `BACKUP_EDGE_SECRET` |

## Rollen-Spezifisches Deployment

### Primärer Windows-Host (Root-Namespace)

```bash
# Dedizierten Docker-Kontext prüfen (NICHT der Produktionstunnel-Anschluss!)
docker context ls
# Falls nötig: neuen Kontext anlegen
docker context create pod-classroom --docker "host=unix:///var/run/docker.sock"

docker compose \
  --project-name pod-racing-primary \
  --env-file ~/private/pod-classroom.env \
  -f compose.yaml \
  -f compose.password.yaml \
  -f deploy/compose.codeweek-common.yaml \
  -f deploy/compose.codeweek-primary.yaml \
  config > /dev/null   # Validierung vor Start
```

### macOS Reserve-Rolle (`/backup` Prefix)

```bash
docker compose \
  --project-name pod-racing-mac-backup \
  --env-file ~/private/pod-classroom.env \
  -f compose.yaml \
  -f compose.password.yaml \
  -f deploy/compose.codeweek-common.yaml \
  -f deploy/compose.codeweek-backup.yaml \
  config > /dev/null   # Validierung
```

## Backup und Restore mit dem portablen CLI

### Backup (auf einem laufenden Host)

```bash
uv run python scripts/classroom_backup.py \
  --context <docker-kontext> \
  --expected-endpoint "unix:///var/run/docker.sock" \
  backup \
  --project pod-racing-primary \
  --container app \
  --volume <existing-volume-name> \
  --output ~/private/classroom-backup-$(date +%F) \
  --gate-container gate

# Nur das Manifest (ohne Hashes / Secrets) erscheint im Terminal.
# Vollständiges Backup inkl. privater Dateien liegt im Output-Pfad.
```

### Restore auf neuer Hardware

```bash
uv run python scripts/classroom_backup.py \
  --context <docker-kontext> \
  --expected-endpoint "unix:///var/run/docker.sock" \
  restore \
  --backup ~/private/classroom-backup-YYYY-MM-DD \
  --new-volume pod-classroom-restored-data \
  --image pod-classroom-release:sha256:<digest>

# Ergebnis ist ein neuer, leergebundener Docker-Volume; die App wird
# automatisch NICHT gestartet. Anbindung erfolgt manuell über das passende
# Compose-Profil mit POD_DATA_VOLUME=pod-classroom-restored-data.
```

## Cloudflare Tunnel-Anbindung (Reserve-Rolle)

Dieser Schritt erfordert Zugriff auf den bestehenden Cloudflare-Account:

1. **Neuer Tunnel** für macOS Reserve erstellen:
   ```bash
   cloudflared tunnel create codeweek-mac-backup
   ```
2. **DNS CNAME** `mac-backup-origin.codeweek-wi.de` auf die neue Tunnel-UUID.
3. **Tunnel Route**: nur `/backup*` weiterleiten (`/backup{,/*}`), Origin `http://127.0.0.1:8766`.
4. **Cloudflare Worker** `pod-classroom-mac-backup` aus `deploy/cloudflare/backup-worker.mjs` deployen; Secret `BACKUP_EDGE_SECRET` mit demselben Wert wie `POD_BACKUP_EDGE_SECRET` befüllen.
5. **SSL-Modus**: `Full` beiderseits (kein Flexible, kein Strict ohne Origin-Zertifikat).

**Nicht verbinden**: Der Primärserver muss exklusiv bleiben; keine Shared-Tunnels, keine gemeinsame Tunnel-ID. Die bestehende Windows-Konfiguration (`codeweek to Haga`, UUID `cd4c4d2e-…`) darf nicht berührt werden.

## Update eines bestehenden Reserve-Rechners

```bash
git switch main          # (bzw. den aktuellsten Branch)
git pull --ff-only
# Optional: Tests erneut ausführen
uv run pytest -m "not docker"
# Dann wie oben Compose-Validierung + ggf. Rollstart mit neuem Image-Tag.
# Vorher: Backup des alten Volumes anlegen (s.o.).
```

## Sicherheitshinweise

- **Keine Credentials in Git**: `POD_SITE_PASSWORD_HASH`, Tunnel-Token und Teacher-Tokens bleiben immer privat.
- **MX / E-Mail unangetastet** bei DNS-Änderungen: SPF, DKIM und DMARC-Einträge sind produktiv und dürfen nicht gelöscht/überschrieben werden.
- **Einzelverantwortung**: Nur ein Gateway pro Cloudflare-Tunnel; das Windows-Gateway läuft weiterhin auf dem bisherigen Rechner.
- **Kein studentischer Release**: Änderungen betreffen nur die geschützte Betriebskonfiguration; kein Unterrichtszugang wird dadurch freigegeben.

## Versionsverlauf (relevant)

| Commit | Thema |
|--------|-------|
| `1b9682d` | Deployment profiles, Backup CLI, edge Worker (PR #8) |
| `427e8d5` | Optionaler Basis-Pfad (`/backup`) und isolierte Cookies/Routes |
| `5533d60` | Handoff-Dokumentation (public continuation instructions) |
