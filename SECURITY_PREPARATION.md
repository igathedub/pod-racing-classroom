# Vorbereitung einer kontrollierten Internetfreigabe

Diese Maßnahmen sind **Basisschutz, keine Freigabe für ungeschütztes Internet-Hosting**. Die Anwendung kann Code ausführen und verwaltet eine Docker-Engine. Vor Schülerzugriff müssen der optionale Klassenzugang und getrennte Lehrkräfte-Authentifizierung aktiviert/geprüft werden; Edge-Missbrauchsschutz und eine unabhängig geprüfte Ausführungsisolation bleiben nötig.

## Optionaler Klassenzugang umgesetzt, externe Freigabe weiter offen

[README.de.md](README.de.md#optionaler-zeitlich-begrenzter-klassenzugang) beschreibt
`POD_CLASS_ACCESS_REQUIRED=1`, Einladungscodes, maximal 60 persistierte Sitzungen,
sofortigen Widerruf und individuelle Budgets. Standardmäßig bleibt der Schutz
für abwärtskompatiblen privaten Betrieb aus. Die API-Prüfungen ersetzen weder
Cloudflare Access noch Edge-DoS-Schutz oder Ausführungsisolation. Ein anonym
öffentlicher Betrieb wird damit ausdrücklich nicht als bereit erklärt.
Container-Healthchecks lesen ausschließlich `/api/health`, keine Kursdaten.
Einladungscodes bleiben aus Startup-Logs und öffentlichen Antworten heraus;
die bereits bestehenden Teacher-Token-Startup-Logs bleiben vertraulich.

## Vorbereitet

- Content Security Policy: Skripte/Styles nur aus der Anwendung, keine Inline-Skripte, kein `unsafe-eval`, keine fremden Frames/Plugins. Die Oberfläche benötigt keinen externen CDN.
- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` und eingeschränkte Kamera-/Mikrofon-/Standort-Berechtigungen.
- API-Antworten einschließlich Claim-Tokens und Lehrkräfte-Codeinspektion sind `Cache-Control: no-store`.
- Schreibende Browser-Anfragen werden gegen exakte Origins geprüft. Fremde Origin-/Referer-Werte und `Sec-Fetch-Site: cross-site` werden verweigert. Das ist Defense-in-Depth, **keine Authentifizierung**: Nicht-Browser-Clients können diese Header weglassen oder fälschen und benötigen weiterhin gültige Admin-/Claim-Berechtigungen beziehungsweise bei aktiviertem Klassenzugang eine Einladung.
- Optionales Host-Allowlisting. Hostnamen werden ohne Ports eingetragen; Wildcards und URL-Pfade sind ungültig. Ohne konfigurierte Liste bleibt die private LAN-/Tailscale-Nutzung kompatibel.
- Prozessweite, feste 60-Sekunden-Anfragefenster für POST `/api/submissions` und `/api/practice`. Standard: 240 beziehungsweise 60 **Versuche** pro Fenster. Auch ungültige Versuche verbrauchen Budget. Nach Ausschöpfung folgt HTTP 429 mit `Retry-After`; Lesen und Lehrkräfte-Aktionen bleiben von diesen beiden Budgets unberührt.
- Budgets sind insgesamt pro Serverprozess, nicht pro IP oder Schüler. So teilt eine Schulklasse hinter NAT nicht versehentlich ein kleines individuelles IP-Limit. Sie sind **keine Garantie gegen DoS oder für Teilnehmer-Fairness**: Ein Angreifer könnte das gemeinsame Budget verbrauchen. Der optionale Klassenzugang ergänzt teilnehmerbezogene Budgets; Edge-Schutz bleibt erforderlich. Ein Fensterwechsel kann kurzfristig einen doppelten Burst erlauben; nach Neustart beginnen die Zähler neu. Nur ein Classroom-Serverworker verwenden.
- `X-Forwarded-For`, `CF-Connecting-IP` und andere vom Client gesetzte Proxy-Header erzeugen weder eigene Budgets noch Origin-Berechtigungen. Keine pauschale Uvicorn-Konfiguration `--forwarded-allow-ips '*'` einsetzen.

## Konfiguration für den geschützten Tunnel-Test

Vor Änderung eine konsistente Sicherung erstellen und bestehende `.env`-Werte erhalten. Die tatsächlich benötigte Host-/Origin-Liste setzen, beispielsweise:

```dotenv
POD_PUBLIC_ORIGINS=https://codeweek-wi.de
POD_ALLOWED_HOSTS=codeweek-wi.de,localhost,127.0.0.1
POD_SUBMISSIONS_PER_MINUTE=240
POD_PRACTICE_PER_MINUTE=60
```

Soll der bisherige Tailscale-Zugriff erhalten bleiben, zusätzlich die **tatsächliche** Tailscale-IP und den verwendeten MagicDNS-Host zu `POD_ALLOWED_HOSTS` ergänzen. Bei mehreren erlaubten öffentlichen Origins kommagetrennte vollständige HTTP(S)-Origins ohne Pfad eintragen. `www` erst hinzufügen, wenn es bewusst eingerichtet wurde. Die Liste muss `127.0.0.1` für den Container-Healthcheck erlauben.

Compose reicht diese HTTP-Einstellungen und die optionalen Zugangseinstellungen aus README.de.md an den Anwendungscontainer weiter. Ein `.env`-Edit allein ändert keinen bereits laufenden Container. Neu erstellen erst nach Backup, abgeschlossenen Turnieraufträgen und geprüftem Rückfallweg:

```text
docker compose up --build -d
```

`POD_BIND` und `POD_PORT` dabei nicht unbeabsichtigt verändern. Für einen hostseitigen cloudflared-Connector die tatsächlich erreichbare interne Bind-Adresse als Tunnelziel verwenden; nicht blind localhost einsetzen. Browser-HTTPS darf intern auf HTTP weitergeleitet werden: die explizite öffentliche Origin erlaubt diese Zuordnung, ohne untrusted Proxy-Header zur Autorisierung zu verwenden.

## Freigabereihenfolge

1. Mail-DNS sichern/übernehmen; Domainaktivierung und HTTPS prüfen.
2. Cloudflare Access **für den gesamten Hostnamen** einrichten, zunächst nur für die erlaubte Lehrkräfte-E-Mail. Keine Everyone-/Bypass-Policy.
3. Origin-/Access-JWT-Prüfung und direkte Origin-Erreichbarkeit passend absichern.
4. Erst dann die Tunnel-Route veröffentlichen; extern ohne Tailscale und ohne Login muss Zugriff verweigert werden.
5. Admin-Token kontrolliert erneuern. Er liegt in SQLite; `POD_ADMIN_TOKEN` gilt nur beim ersten Anlegen und ersetzt keinen bestehenden Token. Sicherung/Datenvolumen niemals zum Rotieren löschen.
6. Den optionalen Klassenzugang ausdrücklich aktivieren und prüfen; Teilnehmerbudgets und getrennte Adminauthentifizierung ersetzen keine geprüfte isolierte Ausführungsumgebung. Schülerzugriff erst nach unabhängiger Freigabe öffnen.

Sitzungen, Quellcode und Tokens nicht veröffentlichen. Die derzeitigen Startup-Logs enthalten den Teacher-Token und müssen privat bleiben. CSP-Frame-Schutz bedeutet, dass fremde Websites die Anwendung nicht einbetten können; reguläre Browseransichten und Projektor-Vollbild bleiben möglich. HSTS/HTTPS-Weiterleitung zunächst an der geprüften Cloudflare-HTTPS-Schicht konfigurieren, nicht anhand beliebiger Client-Proxy-Header.

## Tests

```text
uv run python -m pytest -q
uv run python -m ruff check arena/http_security.py tests/test_http_security.py tests/test_http_budget.py
```

Chromium-Layouttests übernehmen tatsächliche Sicherheitsheader, überwachen CSP-Verstöße und verwenden Funktionsausdrücke statt eval-basierter String-Polling-Prädikate.

## Primärquellen

- HTTP-Sicherheitsheader: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
- Origin-/Referer-/Fetch-Metadata-Prüfung und CSRF-Grenzen: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- Mehrschichtiger DoS-Schutz: https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html
- Access und Origin-Tokenprüfung: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/
