# Primärserver und Reserve: Wiederherstellung und Updates

Für Feature-Freigabe und versionierten Rollout auf beide Hosts: **[ROLLOUT.md](ROLLOUT.md)**. Die folgenden geschützten Beispielprofile sind keine Anweisung, später bewusst deaktivierte Website-/Klassensperren wieder einzuschalten. Beim Update den tatsächlichen aktuellen Zugangszustand und private Overrides erhalten; historische 401-Abnahmen unten gelten nur für den jeweils geschützten Betriebsmodus.

**GitHub liefert Quellcode und öffentliche Betriebsvorlagen, nicht die Unterrichtsdaten.** Ein vollständiger Wiederaufbau benötigt zusätzlich ein geprüftes, privates Backup des jeweiligen Servers samt Website-/Tunnel-Secrets. Die Reserve ist eine unabhängige Installation, **keine automatische Replikation** des Windows-Datenbestands. Ein Klon allein stellt keine Abgaben, Replays, Lehrkraft- oder Klassenzugänge wieder her.

## Rollen und Sicherheitsgrenzen

| Rolle | Öffentlicher Einstieg | Bestehendes Compose-Projekt¹ | Bestehendes Datenvolume¹ |
|---|---|---|---|
| Windows-Primärserver | `https://codeweek-wi.de/` | `pod-racing-classroom` | `pod-racing-classroom_classroom-data` |
| Mac-Reserve | `https://codeweek-wi.de/backup/` | `pod-classroom-local` | `pod-classroom-local_classroom-data` |

¹ Dokumentierter Bestand, vor jedem Eingriff auf dem Zielrechner erneut prüfen. **Bei einem Update bestehende Projekt-/Volumenamen erhalten**, nicht aus dem neuen Klonpfad ableiten. Auf Ersatzhardware kann ein ausdrücklich neu restauriertes Volume angebunden werden. Nie ein fehlendes Datenvolume automatisch durch ein leeres ersetzen.

- Tests: eigener bestätigter lokaler Docker-Endpunkt, eigene Images/Container/Volumes; eine Kontext-Alias allein isoliert **keinen** Docker-Daemon.
- Betrieb: Kontext/Endpunkt des jeweils autorisierten Servers bestätigen. Windows Docker Desktop muss Linux-Container verwenden.
- Compose ≥ 2.24.4 (`!reset`/`!override`); Docker, Git, Python 3.11 und `uv` für das Host-Backupwerkzeug. Node.js wird nur für Worker-Tests benötigt.
- Keine `docker compose down -v`, Volume-/Image-Pruning, Daten-Resets, Tunnel-Umschaltungen oder Lernendenfreigabe durch einen Updateauftrag.
- Keine privaten Dateien, Hashwerte, Tokens oder Datenbankinhalte in Git, Chat, PRs oder Logs kopieren. Keine ungefilterten Docker-Inspect-/Compose-Konfigurationen ausgeben; sie können Secrets enthalten.

## Quellcode auf dem anderen Rechner aktuell halten

Im **bestehenden** Checkout (PowerShell oder macOS-Terminal):

```text
git status --short
git fetch origin
git switch main
git pull --ff-only
git rev-parse HEAD
uv sync --frozen --python 3.11
uv run playwright install chromium
uv run python -m pytest -m "not docker"
node --test deploy/cloudflare/test-worker.mjs
```

Bei lokalen Änderungen oder nicht möglichem Fast-forward stoppen und die Abweichung untersuchen; kein automatisches Reset/Stash. Node-Befehl nur mit installiertem Node.js. Für Ersatzhardware lautet der korrekte Klonbefehl:

```text
git clone https://github.com/igathedub/pod-racing-classroom.git
```

**`git pull` aktualisiert keine laufenden Container.** Eine geplante Betriebsaktualisierung benötigt zusätzlich die Schritte unten. Keine automatischen Neustarts während einer Programmierphase oder eines Turniers. Zur regelmäßigen Kontrolle kann das andere Hermes `git fetch` und einen Versionsvergleich durchführen und ein geeignetes Wartungsfenster melden; die Veröffentlichung neuer Commits ist kein Deploymentauftrag.

## Privates Wiederherstellungspaket

Außerhalb jedes Git-Repositories, mit privaten Dateirechten speichern:

1. Gesamtes `/data` aus einem ruhenden, konsistenten Snapshot: SQLite samt Nebenfiles und alle Replay-Dateien.
2. Bestehende Website-Zugangsdaten/Argon2id-Hash und private Operator-Env-Datei **je Rolle**. Nicht beide Rollen mit dem gleichen Passwort initialisieren oder existierende Passwörter implizit rotieren.
3. Privater Token/Anmeldedateien **des passenden** Cloudflare-Tunnels. Primär- und Reserve-Tunnel nicht vermischen.
4. Reserve zusätzlich: Worker-Secret `BACKUP_EDGE_SECRET` und identischer Origin-Wert `POD_BACKUP_EDGE_SECRET`.
5. Quellcode-SHA, ursprüngliche Image-IDs/Tags, Projekt-/Volumenamen sowie Autostartbeschreibung. Für einen Offline-Restore zusätzlich die benötigten App-/Bot-/Caddy-Images mit `docker image save` privat sichern. Das Daten-CLI exportiert **keine** Images automatisch.

Lehrkraft-Token, Abgaben-Schlüssel und Unterrichtssitzung werden über die unveränderte Datenbank erhalten. Keine neue leere Installation als Ersatz für einen Restore starten. Private Pakete verschlüsselt auf einem zweiten Datenträger/Rechner sichern; ein Backup ausschließlich auf dem ausfallgefährdeten Rechner reicht nicht.

`deploy/operator.env.example` ist nur eine **leere Vorlage**. Auf bestehenden Hosts von der vorhandenen privaten Konfiguration ausgehen und Secrets unverändert übernehmen. Beispielwerte für gültige getrennte Image-Tags: `pod-classroom-primary:<git-sha>` und `pod-classroom-primary-bot:<git-sha>` bzw. entsprechende `backup`-Tags. Ein Registry-Digest hat die Syntax `repository@sha256:<digest>`, **nicht** `repository:sha256:<digest>`. App und Bot sind zwei verschiedene Images.

## Private Dateirechte

POSIX: privates Stammverzeichnis `0700`, Dateien `0600`; keine Links. Beispiel für ein **neues** privates Verzeichnis:

```bash
mkdir -m 700 "$HOME/pod-classroom-private"
```

Windows: dediziertes Verzeichnis mit deaktivierter Vererbung und Zugriff nur für den aktuellen Betreiber sowie bei Bedarf `SYSTEM`/lokale Administratoren. Das Werkzeug prüft Eigentümer und Allow-ACEs anhand von SIDs; `chmod` ersetzt keine Windows-ACL. Bei übertragenen Backups Eigentümer/ACLs rekursiv auf dem Zielrechner prüfen. Die nativen Windows-ACL-Pfade müssen dort nochmals verifiziert werden; die lokale Docker-Abnahme läuft auf macOS.

## Backup-CLI: bestätigter lokaler Docker-Endpunkt

Zuerst nur Metadaten prüfen:

```text
docker context ls
docker context inspect <Kontext> --format "{{.Endpoints.docker.Host}}"
docker --context <Kontext> info --format "{{.OSType}}"
docker --context <Kontext> ps --format "{{.Names}} {{.Status}}"
```

`--expected-endpoint` muss exakt dem vorher geprüften lokalen Endpunkt entsprechen: macOS/Linux `unix:///…`, Windows z.B. `npipe:////./pipe/…`. Keine Unix-Socket-Vorlage ungeprüft auf Windows übernehmen. Kontextname/Endpunkt sind **keine** Servermigration. Der Host-Endpunkt ist nicht zwangsläufig derselbe Pfad wie `POD_DOCKER_SOCKET`, der in den vertrauenswürdigen Appcontainer gemountet wird.

Alle folgenden CLI-Aufrufe sind absichtlich **einzeilig**, damit sie auch in PowerShell funktionieren; Platzhalter erst durch auf diesem Rechner bestätigte Werte ersetzen:

```text
uv run python scripts/classroom_backup.py --help
uv run python scripts/classroom_backup.py --context <Kontext> --expected-endpoint <Endpunkt> inspect --project <bestehendes-Projekt> --container <exakter-Appcontainer> --volume <bestehendes-Volume>
uv run python scripts/classroom_backup.py --context <Kontext> --expected-endpoint <Endpunkt> backup --project <bestehendes-Projekt> --container <exakter-Appcontainer> --volume <bestehendes-Volume> --gate-container <exakter-Gatecontainer> --output <neuer-privater-Backupordner> --private-file <private-Operator-env> --private-file <privater-Tunnel-token-file>
uv run python scripts/classroom_backup.py check --backup <privater-Backupordner>
```

`--private-file` ist wiederholbar und ausdrücklich nötig, wenn Secrets mitgesichert werden sollen. Ohne diese Argumente wird nur `/data` gesichert. Secrets bleiben im privaten Paket; das vollständige Manifest wird **nicht** auf stdout ausgegeben. Das CLI meldet nur Zählwerte und Status.

Ablauf: Projekt/Volume prüfen, offene Programmierphase oder laufenden Job verweigern, Gate schließen, Ruhe erneut prüfen, **denselben** Appcontainer stoppen, kalte Datenkopie prüfen und originalen Appcontainer vor dem Gate wieder starten. Kein Compose-Rebuild beim Backup. Abbruchpakete tragen `.incomplete`; fehlgeschlagene Backups behalten einen exklusiven Lock zur privaten Diagnose. Ein vorhandener Lock darf nicht blind entfernt werden.

## Wiederherstellung auf Ersatzhardware

1. `main` klonen; für einen exakten Rollback den im privaten Paket aufgezeichneten Quellcode-SHA auschecken.
2. Passende private Dateien mit privaten ACLs übertragen. App-/Bot-Images entweder aus dem privaten Imagearchiv laden oder aus dem aufgezeichneten Quellstand bauen; niemals ein fremdes Image als vertrauenswürdigen Restore-Helfer verwenden.
3. Backup überprüfen und **in ein garantiert noch nicht existierendes Volume** restaurieren:

```text
uv run python scripts/classroom_backup.py check --backup <privater-Backupordner>
uv run python scripts/classroom_backup.py --context <Kontext> --expected-endpoint <Endpunkt> restore --backup <privater-Backupordner> --new-volume <neuer-eindeutiger-Volumename> --image <vorhandenes-vertrauenswuerdiges-Appimage>
```

4. Restore verifiziert Dateien/SQLite durch Rückkopieren aus einem isolierten, nicht gestarteten Helfercontainer. Bereits existierende Volumes werden abgewiesen, selbst wenn leer. Bei einem Fehler bleibt ein eventuell neu erzeugtes Volume zur privaten Diagnose erhalten. **Es wird kein öffentlicher Server automatisch gestartet.**
5. Private Env-Datei auf das restaurierte Volume und passende, getrennte App-/Bot-Images einstellen. Richtiges Compose-Rollenprofil wählen; **erst isoliert ohne Tunnel** starten und vollständigen Restore prüfen.
6. Vor öffentlicher Anbindung: Abgabe-/Replay-Zählwerte, Replay-Dateien, bestehendes Teacher-Token, bestehende Abgabeschlüssel, Sitzung/Job und Zugriffsschutz vergleichen. Keine Secrets ausgeben. Öffentliche Route erst kontrolliert mit Rollback umschalten; alten Connector bei Ersatz desselben Tunnels nicht parallel weiterlaufen lassen.

## Compose-Profile verwenden

Immer diese Kombination, im Repository-Wurzelverzeichnis und mit explizitem bestehendem Projekt-/Kontextnamen. PowerShell-Beispiel; Variablen vorab aus bestätigtem Bestand setzen, **nicht** aus Beispielen raten:

```powershell
# $Context, $Project und $PrivateEnv sind vorher bestaetigte lokale Werte.
# $Role ist "primary" fuer Windows-Root oder "backup" fuer die Reserve.
$ComposeArgs = @("--project-name", $Project, "--env-file", $PrivateEnv,
  "-f", "compose.yaml", "-f", "compose.password.yaml",
  "-f", "deploy/compose.codeweek-common.yaml",
  "-f", "deploy/compose.codeweek-$Role.yaml")
docker --context $Context compose @ComposeArgs config --quiet
```

Unter macOS entsprechend `docker --context "$CONTEXT" compose --project-name "$PROJECT" --env-file "$PRIVATE_ENV" -f compose.yaml -f compose.password.yaml -f deploy/compose.codeweek-common.yaml -f "deploy/compose.codeweek-$ROLE.yaml" config --quiet`.

`config --quiet` zeigt keine Hashes/Secrets. Die Release-Profile verlangen explizite `POD_APP_IMAGE`, `POD_BOT_IMAGE` und ein **existierendes externes** `POD_DATA_VOLUME`; die App hat keinen veröffentlichten Hostport. Nur das Caddy-Gate bindet `127.0.0.1:8766`. Bei einem isolierten Paralleltest wegen Portkonflikt einen **eigenen** Loopback-Port per Test-Overlay wählen; nicht das Live-Gate stoppen. Einen ausschließlich lokalen Test nicht mit dem öffentlichen Tunnel verbinden.

## Bestehenden Server kontrolliert aktualisieren

1. Laufende Image-IDs/Tags, Projekt, Volume, private Env-Datei und Ziel-SHA festhalten. Erst read-only prüfen, ob Unterricht/Turnier aktiv ist. Bei Aktivität das Deployment verschieben.
2. Quellcode aktualisieren und Tests ausführen (oben). Laufende Container bleiben zunächst unverändert.
3. Aktuelles privates Backup einschließlich Operator-/Tunnel-Dateien erzeugen und verifizieren. Restore in eigenem Testvolume erfolgreich prüfen. Vor größeren Änderungen auch Imagearchiv für den Offline-Rollback sichern.
4. Neue Image-Tags **je Rolle und Quell-SHA** in einer privaten Kopie der Env-Datei setzen; Volume und Secrets nicht ändern. Mit bestätigtem lokalen Kontext bauen:

```powershell
docker --context $Context compose @ComposeArgs build sandbox classroom
```

5. Neues Image zuerst isoliert abnehmen, dann in genehmigtem ruhigem Wartungsfenster das Live-Gate schließen und mit derselben Projekt-/Volumenzuordnung neu erstellen. Vor Wiederöffnung interne Health/Daten/Zugriffsschutz prüfen. Der tatsächliche Startbefehl (nicht während laufenden Unterrichts):

```powershell
docker --context $Context compose @ComposeArgs stop password-gate
docker --context $Context compose @ComposeArgs up -d --no-build --pull never sandbox classroom
# Erst nach interner Health-/Datenpruefung das Gate wieder oeffnen:
docker --context $Context compose @ComposeArgs up -d --no-deps --no-build --pull never password-gate
```

6. `/api/health` mit den bestehenden Website-Zugangsdaten intern prüfen, dann öffentlich HTTP 401 ohne Anmeldung sowie autorisiert HTTP 200. Primär- und Backup-Ansichten, Teacher-/Projektorpfade und Cookies der richtigen Rolle prüfen. Keine automatische Lernendenfreigabe.
7. Rollback: ursprüngliche Env-/Image-Konfiguration und gegebenenfalls ursprünglichen Quell-SHA verwenden. Das alte Datenvolume **nicht löschen**. Bei inkompatibler Datenänderung das geprüfte Vorabbackup nur in ein neues Volume restaurieren und kontrolliert anbinden, nicht live überschreiben.

## Cloudflare: bestehenden Bestand erhalten

`deploy/cloudflare/topology.json` beschreibt die dokumentierte Solltopologie ohne Credentials; vor Kontoänderungen den tatsächlichen Zustand lesen. **Kein erneutes `cloudflared tunnel create` für einen bestehenden Reserve-Tunnel!** Den passenden bestehenden Connector mit privatem Token auf Ersatzhardware wiederherstellen. Ein neuer Tunnel/DNS-Wechsel ist eine separate, bewusst geplante Umschaltung.

- Primär-DNS: proxied CNAME `codeweek-wi.de` zum vorhandenen **Windows**-Tunnel (`<primär-uuid>.cfargotunnel.com`), nicht zum früheren Website-A/AAAA-Origin. Damit wird der frühere HTTP-525-Pfad nicht wieder eingeführt.
- Beide Connectoren nutzen auf ihrem **jeweiligen Rechner** `http://127.0.0.1:8766`. Ein Cloudflare-Dashboard im Mac-Browser verschiebt keinen Windows-Origin.
- Reserve: eigene Origin-Domain `mac-backup-origin.codeweek-wi.de`, eigener Tunnel; Ingress-Pfad `^/backup(/.*)?$`, richtiger HTTP-Hostheader, abschließende 404-Regel.
- Worker `pod-classroom-mac-backup`: Quellcode `deploy/cloudflare/backup-worker.mjs`, Route **`codeweek-wi.de/backup*`**, `BACKUP_ORIGIN=https://mac-backup-origin.codeweek-wi.de`; private Worker-/Caddy-Marker müssen identisch sein. Worker-Route und Tunnel-Ingress sind **verschiedene** Konfigurationen.
- Worker nur über diese Route bereitstellen, `workers.dev`/Vorschauzugänge deaktiviert lassen. Technischer Origin verweigert Anfragen ohne Marker. Root und Lookalike-Pfade dürfen nicht zur Reserve umgeleitet werden.
- Bestehenden SSL-Modus (dokumentiert `Full`), MX/SPF/DKIM/DMARC und Windows-Tunnel nicht beiläufig ändern. Keine neuen öffentlichen Ports oder Firewallregeln.
- Autostart: bestehende Windows-Dienste bzw. Mac-LaunchAgent mit der jeweiligen privaten Token-Datei rekonstruieren; Tokens nicht in neue Git-Dateien oder CLI-Argumente schreiben. Vor Austausch bestehende Service-Commandlines nicht ungefiltert ausgeben, da alte Installationen Tokens darin enthalten können.

## Startprompt für das Hermes auf dem Windows-Rechner

> Aktualisiere `igathedub/pod-racing-classroom` anhand von `deploy/RESTORE.md` auf den neuesten `main`. Dieser Rechner ist der **bestehende Windows-Primärserver** für `https://codeweek-wi.de/`, nicht die Mac-Reserve. Prüfe zuerst Git-Status, tatsächlich laufende Images, den lokalen Docker-Kontext/Endpunkt, Compose-Projekt, Datenvolume, bestehende private Konfiguration und Unterrichts-/Jobstatus. Bewahre sämtliche Abgaben, Replays, Zugänge, Sitzungen und Windows-Tunnel-Zuordnung. Keine Secrets im Chat/Git, kein Reset/Pruning und kein neues leeres Volume. Quellcode mit Fast-forward aktualisieren und Tests ausführen; das ist noch kein Container-Deployment. Vor einem geplanten Deployment ein geprüftes privates Backup inkl. Operator-/Tunnel-Secrets und einen isolierten Restore-Nachweis erstellen. Neue rollengetrennte Images bauen, im ruhigen Wartungsfenster mit unverändertem Projekt/Volume/Secrets aktualisieren und Zugangsschutz, Datenzahlen sowie Rollback prüfen. Bei aktivem Unterricht/Job keine Container neu starten. Berichte Quell-SHA, laufende Imageversion, Prüfungen und konkrete Blocker getrennt.

## Tatsächlich belegte Prüfungen

PR #8 veröffentlichte die Vorlagen und Basis-Pfad-Unterstützung; seine ursprünglichen 14 Backup-Tests mockten den Docker-Transport. Die nachfolgende CLI-Korrektur ergänzt echte Prozessprüfungen und opt-in Docker-Abnahmetests (`tests/test_backup_docker_acceptance.py`) mit ausschließlich synthetischen Daten für Root **und** `/backup`. Die Tests benötigen explizite `POD_BACKUP_ACCEPTANCE_CONTEXT`, `POD_BACKUP_ACCEPTANCE_ENDPOINT` und `POD_BACKUP_ACCEPTANCE_IMAGE`.

Diese lokale Abnahme ersetzt **keine** native Windows-ACL-Prüfung und **keinen** Restore des privaten Windows-Unterrichtsbestands. Solche Nachweise müssen vom autorisierten Hermes auf dem Windows-Host erbracht werden, ohne die Daten im Bericht offenzulegen.
