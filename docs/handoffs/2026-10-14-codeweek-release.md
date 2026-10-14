# Handoff: codeweek-wi.de / Pod Racing Classroom

Dieser Link ist der vollständige Einstieg für ein anderes Hermes: Repository, Arbeitsstand, Sicherheitsgrenzen, offene Aufgaben und Startprompt sind hier zusammengeführt. Zusätzliche Telegram-Anhänge sind für die Codefortsetzung nicht nötig. **Zugangsdaten und Produktivdaten sind bewusst nicht in GitHub.**

**Nachweisstand: Sitzung vom 14. Oktober 2026.** Betriebs- und Testergebnisse unten stammen aus dieser Sitzung; ein neuer Agent muss die heutige Realität vor Änderungen erneut prüfen. Dieser Dokumentationscommit ist kein Deployment.

## Startprompt für das andere Hermes

> Lies diesen Handoff vollständig und setze die Arbeit an https://github.com/igathedub/pod-racing-classroom fort. Verwende GPT-6.1-sol, auch für alle Subagenten, ohne DGX/Qwen-Fallback. Klone den aktuellen main und prüfe Git-, GitHub-/CI- und Betriebsrealität; behandle die dokumentierten Ergebnisse als historischen Nachweis, nicht als aktuellen Livezustand. Das Produktivsystem bleibt zunächst auf dem bisherigen Windows-Rechner. Keine Migration, Daten-Resets, Volume-/Image-Pruning oder Lernendenfreigabe. Bestehende 20 Abgaben und 61 Replays sowie Unterrichtssitzungen erhalten. Root-Ziel bleibt https://codeweek-wi.de. Der äußere Schutz ist ein separater Caddy-Website-Passwortproxy, kein Cloudflare-Access-Checkout; Lehrerrechte und Klassenzugang bleiben separat. Zuletzt lieferte die öffentliche Domain HTTP 525. Prüfe tatsächliche DNS-/Origin-Records und gespeicherte Tunnelroute im Cloudflare-Konto und stelle die geschützte Bereitstellung fertig. Nutze für Entwicklung nur einen eigenen lokalen Docker-Kontext, eigene Testressourcen und eigenes Volume. Keine Credentials, Passworthashes, Backups oder Lernendencodes in Git, Chat oder Berichten. Berichtssprache Deutsch. UI sagt „Deinen Bot abgeben“ und „Automatisch folgen: AN/AUS“. Arbeite bis zum verifizierten Ergebnis; bei fehlendem Account-/Serverzugang benenne die konkrete benötigte Autorisierung, statt Ergebnisse zu erfinden.

## Ziel und Status

- Unterrichtsanwendung mit getrennten Schüler-, Lehrer- und Projektoransichten; großer Programmiereditor bleibt erhalten.
- Öffentlicher Zielhost: **https://codeweek-wi.de**, keine ungefragt gewählte Subdomain.
- Gesamter Host einschließlich API zunächst mit eigenem Website-Passwort geschützt; zuerst externe Lehrkraft-Generalprobe, Lernende ausschließlich nach ausdrücklicher Freigabe.
- Zusätzlich zeitlich begrenzte Klassencodes und getrennte Teilnehmersitzungen.
- Fremder Python-Code ausschließlich in der begrenzten Docker-Sandbox. Private Testrennen dürfen Ranglisten, Qualifikation, Finale, Archive und Klassenstatus nicht verändern.
- Nachweisstand: Anwendung und Passwortproxy lokal live und geprüft. **Öffentliche Bereitstellung noch nicht fertig:** `/` und `/api/health` lieferten HTTP 525; keine Lernendenfreigabe.

## Git-/Release-Basis

- Repository: https://github.com/igathedub/pod-racing-classroom — zum Zeitpunkt dieses Handoff-Commits öffentlich.
- Geprüfter Anwendungs-/Proxy-Quellstand auf `main`: `96d5ddfb3e24a7fee5ae3047e87173c06b2d7c26`. Neuere Dokumentationscommits ändern nicht automatisch das laufende Image. Bei abweichendem HEAD Änderungen untersuchen, nicht blind zurücksetzen.
- Klassenzugang: [PR #6](https://github.com/igathedub/pod-racing-classroom/pull/6), gemergt; Featurecommit `7c6c2f353120388fbd21d447f6c136f9784e209a`.
- Passwortproxy: [PR #7](https://github.com/igathedub/pod-racing-classroom/pull/7), gemergt; Featurecommit `99865b712a602595e911c0563ec95713bc024957`. Merge-Tree wurde gegen den geprüften Tree verglichen.
- Git-Identität des Auftraggebers: `Igor Dub <20015342+igathedub@users.noreply.github.com>`. Keine separate „assisted by AI“-Identität erzeugen.

## Nachgewiesener Betrieb auf dem bisherigen Windows-Host

- Appcontainer `pod-racing-classroom-classroom-1`: running, healthy, **keine veröffentlichten Hostports**.
- App-Image `sha256:253b1a50cfc85a2c406cb03d224dbeb14a45cc59bccbdf34ad8c01a3a82c4300`, Release-Tag `pod-classroom-release:7c6c2f3`. Anwendungs-Code entspricht dem geprüften Featurestand; PR #7 ergänzt Proxy-Konfiguration, Dokumentation und Tests.
- Proxycontainer `pod-racing-classroom-password-gate-1`: ausschließlich `127.0.0.1:8766` → Containerport 8080.
- Datenvolume `pod-racing-classroom_classroom-data` blieb erhalten.
- Proxy: Read-only Root, cap-drop ALL, no-new-privileges, CPU/RAM begrenzt, kein Docker-Socket. Capability-freie Caddy-Kopie im begrenzten `/run`-tmpfs.
- Website-Passwort und Teacher-Token sind getrennt. Basic Authorization wird vor dem Upstream entfernt. Basic allein gewährt weder Klassen- noch Lehrerrechte.
- Lokal ohne/falsch authentifiziert: 401; korrekt authentifiziert: 200. Alter Backend-Direktzugriff auf Hostport 8765 geschlossen.
- Klassen-Gate und Secure-Cookie aktiviert. Lokale Probe bestätigte getrennte Sitzungen, Secure/HttpOnly/SameSite Strict, keinen Schüler-Adminzugriff und Widerruf. Probeeinladung anschließend widerrufen; keine Botabgaben oder Rennen als Live-Smoke-Test erzeugt.
- **20 Abgaben, 61 Replays und acht verglichene Legacy-Statefelder exakt erhalten. Alle 61 Replays über den geschützten Proxy geladen; Sandboximage unverändert.**
- Windows-Dienste `cloudflared` und `sshd`: Running, Automatic. Das beweist weder eine gespeicherte öffentliche Tunnelroute noch erfolgreiche SSH-Anmeldung von einem anderen Rechner.

## Tests und Reviews aus der Sitzung

- Gesamtsuite: **234 bestanden, 1 opt-in-Test übersprungen**.
- Passwortgate-Suite separat opt-in: **18 bestanden**, einschließlich echtem Docker-/Caddy-/HTTP-Test. Nicht 18 eigenständige reale Docker-Abnahmen.
- Isolierte Klassenabnahme: **23 Prüfungen**, 20 Chromium-Sitzungen/Parallelabgaben, echte private Practices, Qualifikation und Finale, **69 Sandbox-Inspektionen**. Live-Daten blieben unverändert.
- Unabhängiges finales Passwortproxy-Re-Review bestanden, keine Sicherheits-/Logikbefunde. Vorherige Cleanup-Fehler per TDD behoben: exaktes Eigentumslabel, Löschung anhand beobachteter Ressourcen-ID, Fortsetzung nach Timeout/OSError, vollständiges Readback/Leaksuche.
- Node-Syntax und Whitespace geprüft. Lokale Ergebnisse sind kein Nachweis ausgeführter GitHub-CI.
- Zusätzlich Live-Ansichten in eigenem Headless-Chromium **mit eingeschalteter Browser-Sandbox** geprüft: Schüler, Lehrer, Projektor HTTP 200; keine JavaScript-/CSP-Fehler. Lehrer-/Projektorkontexte mit separatem Lehrerheader: 61 Replay-Optionen; nicht beigetretene Schüler: null. Das ist lokale HTTP-Prüfung, **keine externe HTTPS-Generalprobe**.

## Blocker: öffentliche Cloudflare-Anbindung

- Letzte öffentliche HTTPS-Probes auf `/` und `/api/health`: **525**, `Server: cloudflare`, keine Basic-Challenge.
- Cloudflare beschreibt 525 als fehlgeschlagenen SSL-Handshake zwischen Cloudflare und Origin-Webserver.[1] Das belegt keinen TLS-Fehler der lokalen App; der Loopback-Passwortproxy wurde separat erfolgreich geprüft.
- Öffentliche A/AAAA lieferten Cloudflare-Edge-Adressen. Die tatsächliche Origin-Konfiguration ist daraus nicht ablesbar. Frühere Behauptungen einer konkreten Origin-IP oder eines DNS-Konflikts waren nicht ausreichend belegt und dürfen keine Grundlage für Löschungen sein.
- Vorgesehene Tunnelroute: Root-Domain `codeweek-wi.de`, Subdomain/Path leer, Service **`http://127.0.0.1:8766`**. Erfolgreiche Speicherung wurde nicht nachgewiesen; tatsächliche Route und DNS im Konto lesen.
- Chrome-Schließen war ausdrücklich freigegeben und wurde ausgeführt; ein eindeutig identifizierter verwaister Hermes-Snapshot-Prozess wurde gezielt entfernt. Der Browser-Use-Start mit gespeichertem Benutzerprofil scheiterte weiterhin. Keine geschützten Profil-/Cookie-Dateien direkt lesen und keine Browser-Sandbox abschalten.
- Rechner war gesperrt. CLI, Docker und sauberes Headless-Chromium funktionierten dennoch. Keine blinden Kill-/Klickschleifen: entsperrten Desktop oder authentifizierten Browser auf anderem Rechner nutzen. Hermes unterstützt grundsätzlich Headless-Browsing.[2]

## Nächste Aufgaben, in Reihenfolge

1. Aktuellen Quellstand, Container-/Volume-/Portzustand, Datenbestand und private Sicherung prüfen. Keine credentialhaltigen Docker-Logs oder Compose-Env-Werte in Ausgaben übernehmen.
2. Mit sicherem Cloudflare-Accountzugang tatsächlichen Zonenbestand und gespeicherte Tunnel-Konfiguration lesen. Bestehenden Connector auf dem bisherigen Server verwenden. Falls Accountzugang fehlt: genau diesen Zugang anfordern, keine Passwörter/2FA-Codes im Chat sammeln.
3. Root-Hostname an den geprüften Loopback-Passwortproxy anbinden. Ein möglicher Website-A/AAAA-Konflikt muss zuerst im Konto nachgewiesen werden. Nur notwendige Website-Records ändern; **MX/SPF/DKIM/DMARC erhalten**. Keine pauschale Umstellung auf Flexible/SSL-off.
4. Gespeicherte Route und DNS exakt zurücklesen. Öffentliches Routing bei Proxy-/Tunnel-/Originfehlern fail-closed halten; vor Rollback öffentliche Route schließen. Backend niemals direkt veröffentlichen.
5. Externe HTTPS-Abnahme: ohne/falsch → 401 auf Host/API, korrekt → 200; Teacher separat, Schüler niemals Admin. Realen Chromium-/CSP-Klassenworkflow, Cookies, Widerruf und Replayzugriff über HTTPS prüfen. Daten unverändert nachweisen.
6. Lehrkraft-Generalprobe abschließen. Erst danach ausdrückliche Lernendenfreigabe einholen; diese liegt nicht vor.
7. Tatsächlichen Sende-/Empfangstest des bestehenden STRATO-Postfachs durchführen. Öffentliche DNS-Auflösung war geprüft: MX `5 smtpin.rzone.de.`, SPF `v=spf1 redirect=_spf.strato.com`, DMARC `v=DMARC1;p=reject;`, beide `strato-dkim-0002/0003._domainkey`-CNAMEs auf entsprechende `rzone.de`-Ziele. DNS-Erfolg ist kein Mailtest.

## Anderer Rechner: Entwicklung ja, Betriebsumzug nicht automatisch

**Empfehlung:** Entwicklung und Cloudflare-Verwaltung auf dem neuen Rechner, laufenden Betrieb zunächst auf dem alten Windows-Host lassen.

Für Entwicklung benötigt das andere Hermes:

- Hermes mit eingerichtetem GPT-6.1-sol-Provider; auch Subagenten ausschließlich GPT-6.1-sol. Provider-Anmeldungen werden durch Git-Clone nicht übertragen.
- Git und dieses Repository. Zum Veröffentlichungszeitpunkt ist es öffentlich; Schreiben/PRs benötigen autorisierten GitHub-Zugang. Ältere README-Passagen zur privaten Sichtbarkeit sind historisch.
- Python >=3.11 und uv für native Entwicklung; Playwright/Chromium für Browserprüfungen. Für die Docker-Betriebsvariante selbst ist kein Host-Python erforderlich.
- Docker mit Linux-Containern für Sandbox und reale Integrationstests.

```text
git clone https://github.com/igathedub/pod-racing-classroom.git
cd pod-racing-classroom
git checkout main
git pull --ff-only
git rev-parse HEAD
uv sync --frozen --python 3.11
uv run playwright install chromium
uv run pytest -m "not docker"
```

Die Befehle sind eine Startanleitung, keine hier durchgeführte Installation auf dem neuen Rechner. Docker-Tests erst nach Prüfung des Docker-Kontexts/Endpoints: Er darf nicht unbemerkt auf den Produktiv-Docker zeigen. Eigener lokaler Entwicklungsserver: separater Compose-Projektname, z.B. `pod-classroom-dev`, eigenes Volume, Loopback-Bindung. Keine Livecontainer, Livevolumes oder produktiven Image-Tags für isolierte Tests verändern.

Cloudflare kann im Browser des neuen Rechners verwaltet werden. **`127.0.0.1:8766` in der Tunnelkonfiguration bezieht sich auf den Connector-Rechner**, nicht auf den Rechner mit dem Dashboard-Browser. Sichere Anmeldung/Vault verwenden.

Für Fernverwaltung des bisherigen Servers zusätzlich: private Netzwerkerreichbarkeit, zugelassenes Windows-Konto, SSH-Authentifizierung und passende bestehende Firewall-Regeln. Dienststatus allein beweist keinen funktionierenden Remotezugriff. Keine öffentlichen Ports oder neue SSH-/Firewall-Regeln ohne gesonderte Freigabe.

Ein echter Betriebsumzug benötigt dagegen konsistentes privates Backup, sichere Secret-/Tunnel-Credential-Übertragung, getesteten Restore, Sandbox- und Ressourcenprüfung sowie kontrollierte Umschaltung mit Rollback. Diese Migration ist **nicht beschlossen**. Zwei Hermes-Gateways nicht ungeprüft mit demselben Telegram-Bot parallel starten.

## Private Operator-Artefakte und Grenzen

Keine Passwörter, Teacher-Tokens, Passworthashes, API-Schlüssel, Lernendencodes, Datenbanken oder Backups in Git, Chat, PRs oder Berichte aufnehmen. Der Link ersetzt keine Berechtigung zum Cloudflare-Konto oder Produktivhost.

- Private Website-/Release-/Rollback-Dateien befinden sich auf dem bisherigen Host außerhalb des Repositories unter `%LOCALAPPDATA%/hermes/secrets/pod-racing-classroom/website-access`. Werte nur über sichere Operator-/Vault-Wege verwenden.
- Vor-Rollout-Backup `2026-10-14_180456` und Post-Deployment-Backup `2026-10-14_193335` privat bewahrt, SQLite-/Archive geprüft, 20/61 erhalten. Eine frühere Sicherung wurde real in separatem Volume restauriert und nach Neustart geprüft. Backups enthalten Credentials und Lernendencode, niemals als Chat-Datei senden.
- Private Scratch-Helfer sind **nicht Teil des Git-Clones**. Fehlen sie auf dem neuen Rechner, nicht ihre Existenz oder Wirkung behaupten. Am alten Host prüfen oder eine neue, isoliert getestete Operatorlösung erstellen.
- Backuphelfer `backup_codeweek_classroom.py` wurde per TDD von geschlossenem Hostport auf autorisierten Stateabruf innerhalb des vorhandenen Containers umgestellt: 2 RED → 2 GREEN, echter Backup-Lauf erfolgreich; Teacher-Credential verbleibt im Container.
- `prepare_codeweek_protected_release.py` ist ein Vor-Rollout-Artefakt. Nicht erneut ausführen und damit erhaltene Baseline-/Rollback-Metadaten überschreiben.
- Deployment-Scratchhelfer `deploy_codeweek_protected_release.py` besitzt `POD_GATE_VERIFY_ONLY=1`; Deploymentmodus erwartet das alte Pre-Rollout-Image. Nicht ungeprüft erneut deployen.
- Niemals Live-Reset, `docker compose down -v`, Volume-/Image-Pruning oder Live-Wettbewerbe als Smoke-Test. Bestehende Standard-Image-Tags bei isolierten Tests nicht verändern. Keine laufenden Unterrichtssitzungen zurücksetzen.

## Relevante Repository-Dateien

- [Passwortproxy-Betrieb](../password-gate.md)
- [Compose-Passwortgate](../../compose.password.yaml)
- [Caddy-Konfiguration](../../deploy/Caddyfile.password)
- [Passwortgate-Tests](../../tests/test_password_gate_config.py)
- [Klassenzugang](../../arena/class_access.py)
- [API und Zugriffskontrollen](../../arena/app.py)
- [Frontend](../../web/app.js) und [Übersetzungen](../../web/i18n.js)
- [Deutsche Installationsanleitung](../../README.de.md)

## Handoff bei weiterer Arbeit

Berichte kompakt: Scope, Branch/SHA, betroffene Dateien, tatsächlich ausgeführte Prüfungen, GitHub-/CI-Belege, Live-Datenerhalt, Blocker/Risiko und nächster kleinster Schritt. Historische, dokumentierte und frisch verifizierte Aussagen trennen. Git-Push oder Deployment erst nach Readback als erfolgreich melden.

## Sources

[1] https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-525 — Cloudflare Error 525 — SSL handshake failed
[2] https://hermes-agent.nousresearch.com/docs/user-guide/features/browser — Hermes Browser Automation — real profile and headless mode
