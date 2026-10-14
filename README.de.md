# Pod Racing Classroom – deutsche Anleitung

[English documentation](README.md)

Eine lokal betriebene Website für Python-Programmierkurse: Die Lernenden reichen Programme unter einem Alias ein, fahren eine faire Qualifikation und sehen anschließend ein animiertes Finale der besten fünf Bots. Die Oberfläche bietet **Deutsch und Englisch** mit einem Sprachschalter auf jeder Ansicht. Das Spiel ist eine eigenständige Unterrichtsvariante, **nicht** der offizielle CodinGame-Schiedsrichter. Jede Person steuert einen Pod; das Finale mit fünf Pods ist ausdrücklich keine Gold-Liga-Simulation.

## Sprache und Programmierphase

Im Kopfbereich **Deutsch** oder **English** auswählen. Die Auswahl bleibt in diesem Browser gespeichert. Mit `/?lang=de`, `/teacher?lang=de` oder `/projector?lang=de` lassen sich deutsche Ansichten direkt teilen. `?lang=en` wählt Englisch. Ein Sprachwechsel lädt die Seite nicht neu und behält Codeentwürfe, Bot-Namen, private Schlüssel und die Position einer Rennaufzeichnung.

Die Sitzung heißt **Programmierphase** (englisch: **Coding session**); die voreingestellte Abgabezeit bleibt zwei Stunden, also 7200 Sekunden. Anleitungen, Bedienelemente, Regeln, bekannte Fehlermeldungen und Kommentare des Startcodes sind übersetzt. Python-Bezeichner, Protokollwörter, eingereichter Code und Bot-Namen werden nicht verändert. Unbekannte technische Diagnosen bleiben unverändert, statt falsch übersetzt zu werden.

## Auf einem anderen Computer installieren

Benötigt werden nur **Docker mit Docker Compose** und der Quellcodeordner:

- **Windows:** Docker Desktop starten und Linux-Container verwenden, nicht Windows-Container.
- **macOS:** Docker Desktop installieren und starten.
- **Linux:** Docker Engine und das Compose-Plugin installieren; der angemeldete Benutzer muss den Docker-Daemon ansprechen können.

Python, uv, Node.js und npm müssen auf dem Gastgeber-Rechner **nicht** installiert sein. Zum ersten Bau der Images ist Internetzugang nötig. Danach läuft der Unterricht lokal, ohne Cloud-Dienst oder CodinGame-Konto.

1. Den Quellcode als Archiv entpacken oder mit installiertem Git klonen:
   ```text
   git clone https://github.com/igathedub/pod-racing-classroom.git
   cd pod-racing-classroom
   ```
   Das Repository ist privat. Zum Klonen/Herunterladen braucht die Lehrkraft einen berechtigten GitHub-Zugang oder ein vom Eigentümer bereitgestelltes Quellcodearchiv. Die Lernenden brauchen keinen GitHub-Zugang. Keine Zugangsdaten, Datenbanken oder Lehrkraft-Schlüssel mit dem Quellcode weitergeben.
2. Im Projektordner ausführen:
   ```text
   docker compose up --build -d
   docker compose ps
   docker compose logs classroom
   ```
   Warten, bis `classroom` als **healthy** angezeigt wird. Compose baut automatisch das Bot-Image `pod-classroom-bot:local`, lässt einen vertrauenswürdigen Abschlussmarker laufen und startet erst dann die Anwendung. In den Logs steht **Teacher admin token**: Dieser geheime Schlüssel wird für jede neue Dateninstallation zufällig erzeugt, dauerhaft gespeichert und beim Neustart erneut angezeigt. Es gibt kein voreingestelltes Passwort. Die Logs nicht projizieren oder öffentlich teilen.
3. `http://localhost:8765/teacher` öffnen und den Schlüssel eingeben. Die Projektoransicht befindet sich unter `http://localhost:8765/projector`. Standardmäßig ist die Website nur auf diesem Computer erreichbar (`127.0.0.1`).

**Bequemer Start:** Unter Windows `Docker-start.cmd` doppelklicken; unter macOS/Linux `sh Docker-start.sh` ausführen. Beide Varianten bauen/starten die Container, warten auf Betriebsbereitschaft und zeigen den Schlüssel an. Die Container laufen auch nach dem Schließen dieses Fensters weiter.

### Für das Klassenzimmer-Netzwerk freigeben

Eine Datei namens `.env` neben `compose.yaml` anlegen, zum Beispiel:

```dotenv
POD_BIND=0.0.0.0
POD_PORT=8765
```

Danach `docker compose up -d` ausführen. Den Lernenden die Adresse `http://IP-DES-KLASSENZIMMER-RECHNERS:8765/` geben. Die private WLAN-/LAN-Adresse verwenden, nicht die Adresse eines Docker- oder VPN-Adapters. Vor dem Workshop von einem zweiten Gerät testen. Für einen belegten Port kann beispielsweise `POD_PORT=18765` verwendet werden; Links und Firewall-Regeln müssen dann ebenfalls diesen Port verwenden. `POD_BIND` unterstützt die IPv4-Werte `127.0.0.1` und `0.0.0.0`.

Nur in einem **vertrauenswürdigen privaten Netzwerk** freigeben. Keine Router-Portweiterleitung und kein öffentliches Internet-Hosting. Gäste-WLAN blockiert häufig die Verbindung zwischen Geräten. Die Schul-IT kann ein geeignetes Netzwerk und die tatsächliche Erreichbarkeit prüfen; Docker Engine unter Linux kann Ports unabhängig von manchen Host-Firewall-Regeln veröffentlichen.

Optional kann die IT unter Windows als Administrator TCP 8765 ausschließlich für das lokale Subnetz im privaten Netzwerk erlauben:

```powershell
New-NetFirewallRule -DisplayName 'Pod Racing Classroom' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -Profile Private -RemoteAddress LocalSubnet
```

Diese Regel wird nicht automatisch gesetzt. Nach dem Workshop wieder entfernen. Für rein lokale Nutzung `POD_BIND=127.0.0.1` setzen und erneut `docker compose up -d` ausführen.

## Ablauf für die Lehrkraft

1. Docker und die Website starten. Prüfen, dass die Sandbox bereit ist, und den Schüler-Link auf einem anderen Gerät öffnen.
2. In einer leeren Sitzung mit **6 Beispiel-Bots hinzufügen** echte Beispielprogramme einfügen. **Qualifikation starten** und danach **Finale starten** zum Probelauf nutzen. Vor dem Unterricht die Demo über die ausdrücklich bestätigte Reset-Funktion löschen.
3. Unter `/teacher` auf **Programmierphase starten** klicken. Erst dann sind Einreichungen möglich.
4. Die Lernenden wählen einen Alias und fügen ihren Python-Code ein oder laden eine `.py`-Datei hoch. Änderungen sind bis zum Einsendeschluss möglich. Das Browser-Token schützt den Alias; derselbe Browser sollte weiterverwendet werden. Quellcode zusätzlich selbst speichern.
5. Am Ende die Einreichung schließen oder den Countdown ablaufen lassen. Mit **Qualifikation starten** die Qualifikation starten. Alle Programme fahren dieselben drei deterministischen Strecken ohne Kollisionen; ihre Quellcodeversionen werden dabei eingefroren. Fehlerhafte Programme sind nicht fürs Finale zugelassen.
6. Nach abgeschlossener Qualifikation **Finale starten** wählen. Die besten fünf gültigen Programme fahren gemeinsam mit Kollisionen. Bei weniger gültigen Programmen fahren entsprechend weniger, mindestens zwei.
7. `/projector` im Vollbild projizieren. Wiedergabe pausieren, beschleunigen oder erneut ansehen. Der Sieger wird in der Projektoransicht erst am Rennende verraten. Wenn niemand gültig ins Ziel kommt, wird nicht einfach ein abgestürzter Bot zum Sieger erklärt.

Den Lehrkraft-Schlüssel und das Loginfeld nicht projizieren. Sitzung, Deadline und Ergebnisse überstehen einen Neustart. Ein unterbrochener Turnierauftrag wird als fehlgeschlagen markiert, nicht automatisch fortgesetzt. Während eines laufenden Turniers nicht aktualisieren oder zurücksetzen.

## Python-Schnittstelle für die Lernenden

Die Startvorlage gibt es auf der Website. Pro Zug liest ein Programm zwei Zeilen:

```text
x y checkpoint_x checkpoint_y distance relative_angle
opponent_x opponent_y
```

Es gibt genau eine Aktionszeile aus:

```text
target_x target_y thrust
```

- Die Koordinaten sind ganze Zahlen. Die Strecke ist grundsätzlich 16000 × 9000 Einheiten groß.
- `thrust` ist eine Zahl von 0 bis 100; größere/kleinere Ganzzahlen werden begrenzt. Einmal pro Rennen ist `BOOST` möglich; weitere BOOST-Befehle wirken wie Schub 100.
- `SHIELD` macht den Pod für den Aktivierungszug und die zwei folgenden Züge schwerer und verhindert Schub. Nach der freien Ausrichtung im ersten Zug kann der Pod höchstens 18 Grad pro Zug drehen.
- Im Finale bezeichnet die Gegnerzeile den **nächstgelegenen anderen Pod**, nicht immer denselben Gegner.
- Beide Eingabezeilen in jedem Durchlauf lesen. Variablen außerhalb der Schleife behalten ihren Wert über mehrere Züge.
- Aktionen mit `print(..., flush=True)` ausgeben; Debug-Ausgaben gehören nach `sys.stderr`.
- Die Sandbox enthält nur die Python-Standardbibliothek, keine Zusatzpakete. Einreichungen erhalten weder Netzwerkzugriff noch Host-Dateien.

Die Regeln auf der Website sind für das tatsächlich implementierte Spiel maßgeblich. Zwei Runden, maximal 700 Züge, begrenzte Antwortzeit und begrenzte Ausgabe verhindern endlose Rennen. Einsteiger können zunächst Checkpoints ansteuern und danach Kurvenverhalten, Bremsen und den BOOST-Zeitpunkt verbessern.

## Stoppen, aktualisieren und Daten behalten

```text
docker compose stop
docker compose start
docker compose logs classroom
```

`docker compose down` entfernt Container und Netzwerk dieses Projekts, **nicht** die gespeicherten Daten. Anschließend mit `docker compose up -d` starten. Nach einer Quellcodeaktualisierung `docker compose up --build -d` ausführen. Dazu vorher laufende Turniere beenden.

Die Daten liegen im projektbezogenen benannten Volume `classroom-data`, im Container unter `/data`: Einreichungen, gespeicherte Quellcodeversionen, Sitzung, Replays und Lehrkraft-Schlüssel. Für Updates denselben Ordner/Compose-Projektnamen behalten. Ein anderer Ordnername oder ein anderes `-p` kann ein anderes Volume auswählen; bei ausdrücklich gewähltem Projektnamen immer `docker compose -p IHR-NAME ...` verwenden.

**`docker compose down --volumes` löscht die Unterrichtsdaten samt Lehrkraft-Schlüssel. Dies nicht versehentlich ausführen!** Die Starthelfer löschen keine Volumes. Die Reset-Funktion der Lehrkraft-Seite löscht den Wettbewerb, behält aber den Schlüssel. Nur den Quellcode auf einen anderen Rechner zu kopieren erstellt eine neue leere Installation; es überträgt keinen laufenden Wettbewerb. Für ein Backup die Anwendung stoppen und das gesamte `/data`-Volume mit einem vertrauenswürdigen Volume-Backup-Werkzeug sichern. Für eine Übernahme auf einem anderen Rechner das vollständige Volume wiederherstellen. Backups enthalten private Schlüssel und Schülercode: vertraulich behandeln.

## Sicherheit und Docker-Socket

Vorbereiteter HTTP-Basisschutz und der Ablauf für einen **zunächst ausschließlich für Lehrkräfte geschützten Tunnel-Test** sind in [SECURITY_PREPARATION.md](SECURITY_PREPARATION.md) dokumentiert. Diese Vorbereitung ist keine Freigabe für ungeschützten öffentlichen Schülerbetrieb; die unten beschriebenen Docker-Risiken bleiben bestehen.

Hochgeladener Code läuft ausschließlich in eingeschränkten, getrennten Docker-Containern: ohne Netzwerk, ohne Host-Mounts, als nicht privilegierter Benutzer, mit schreibgeschütztem Dateisystem, verworfenen Linux-Capabilities und Ressourcen-/Ausgabelimits. Fehlt Docker oder das Sandbox-Image, wird die Ausführung verweigert; es gibt keinen unsicheren Fallback auf den Host.

**Die Anwendung selbst erhält `/var/run/docker.sock`. Dieser Zugriff ist einer Host-Administratorberechtigung gleichzusetzen.** Die Anwendung ist vertrauenswürdige Verwaltungssoftware und läuft für gängige Socket-Berechtigungen als root. **Schüler-Bots erhalten niemals diesen Socket oder andere Host-Mounts.** Auch ein schreibgeschützt eingebundener Socket ist keine Sicherheitsgrenze. Keinen ungesicherten TCP-Docker-Daemon verwenden und die Website nicht öffentlich zugänglich machen. Docker ist eine praktische Isolation, keine Garantie gegen jede Kernel-/Runtime-Sicherheitslücke. Docker aktuell halten; für feindliche öffentliche Einreichungen eine isolierte, entbehrliche VM verwenden.

### Rootless Docker unter Linux

In `.env` den tatsächlichen Socket-Pfad setzen, beispielsweise:

```dotenv
POD_DOCKER_SOCKET=/run/user/1000/docker.sock
```

1000 durch die eigene Benutzer-ID beziehungsweise den tatsächlichen Pfad ersetzen. Der Compose-Client auf dem Host muss denselben Daemon ansprechen: passenden Docker-Kontext wählen oder `DOCKER_HOST=unix:///run/user/1000/docker.sock` setzen. Im Anwendungscontainer verweist `DOCKER_HOST` ausdrücklich auf den eingebundenen Linux-Socket `/var/run/docker.sock`; Windows-Einstellungen mit `npipe://` werden nicht übernommen. Ein fehlender Socket wird nicht als Verzeichnis angelegt. Remote-Docker-Kontexte sind nicht der Standardfall; Build, Bot-Image und eingebundener Socket müssen zum selben Linux-Daemon gehören. Bei rootless Docker hängt die Durchsetzung der Ressourcenlimits von der cgroup-Unterstützung ab: auf dem Zielrechner vorab prüfen.

Die per Digest festgelegten Basisimages für Python, uv und Docker CLI enthalten Linux-AMD64-/ARM64-Varianten. Es wird keine Architektur erzwungen. **Tatsächlich geprüft:** Linux-AMD64-Anwendungscontainer unter Docker Desktop auf Windows, echte Qualifikation mit sechs Bots, Finale mit fünf Bots sowie Daten-/Schlüsselerhalt nach Neustart und Container-Neuerstellung. macOS, natives Linux und ARM64-Hardware wurden hier nicht getestet. Vor dem Unterricht auf dem Zielrechner den Demo-Wettbewerb durchführen.

## Probleme beheben

- **Docker nicht bereit / unhealthy:** Docker starten, Linux-Container wählen, `docker compose logs classroom` und `docker compose ps` prüfen. Stimmen Docker-Kontext und Socket überein?
- **Port belegt:** `POD_PORT` in `.env` ändern und `docker compose up -d` erneut ausführen.
- **Schüler-Link nicht erreichbar:** `POD_BIND=0.0.0.0`, richtige private LAN-IP und Port prüfen; Firewall und WLAN-Geräteisolation mit der IT klären.
- **Privates Repository nicht zugänglich:** Git mit einem berechtigten Konto anmelden oder ein Quellcodearchiv vom Eigentümer erhalten. Keine Zugangstokens in geteilte Befehle oder Dokumente schreiben.
- **Lehrkraft-Schlüssel vergessen:** `docker compose logs classroom`. Auch beim Neustart wird derselbe gespeicherte Schlüssel erneut ausgegeben. Das Volume dafür nicht löschen.

## Alternative und Entwicklung

Die bisherigen Windows-Dateien `Setup.cmd` und `Start-classroom.cmd` bleiben für die native Python-/uv-Installation verfügbar; siehe [README.md](README.md). Sie sind für den Docker-Compose-Weg nicht erforderlich.

Optionaler Entwicklertest mit Python/uv:

```text
uv run python scripts/deployment_test.py
```

Er baut ein zufällig benanntes Compose-Testprojekt, verwendet ein Wegwerf-Volume und einen freien localhost-Port, fährt eine echte Qualifikation und ein Finale, prüft den Erhalt von Schlüssel/Ergebnissen/Replays nach Neustart und Neuerstellung und entfernt nur seine eigenen Testcontainer und sein Volume. Das gemeinsame Bot-Image bleibt erhalten. Ergebnisdatei: `artifacts/deployment-result.json`.

Originalquellcode: MIT-Lizenz; Abhängigkeiten behalten ihre eigenen Lizenzen. Architektur: FastAPI, SQLite, deterministische Python-Engine, Docker-Bots und HTML/JavaScript-Canvas, ohne Frontend-Build oder CDN.
