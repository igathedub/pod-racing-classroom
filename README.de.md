# Pod Racing Classroom

**Python-Bots. Faire Qualifikation. Ein Klassenfinale auf drei Strecken.**

Entwickelt für die **Codeweek 2026 in Wiesbaden**. Eine selbst betriebene Unterrichtswebsite mit deutscher/englischer Lernenden-, Lehrkraft- und Beameransicht, Alias-Abgaben, privaten Testrennen und animierten Rennaufzeichnungen. Lernende brauchen einen Browser; die Lehrkraft betreibt Docker.

Ein eigenständiges, von CodinGame inspiriertes Unterrichtsspiel, **kein offizieller Referee und kein mit CodinGame verbundenes Produkt**. Jede Person steuert einen Pod; das Fünferfinale ist keine Gold-Liga-Simulation mit zwei Pods je Team.

[English](README.md) · [KI-gestützte Einrichtung](docs/agent-setup.md) · [Sicherheit](SECURITY.md) · [Mitmachen](CONTRIBUTING.md) · [MIT-Lizenz](LICENSE)

![Echte Beameransicht der Anwendung mit synthetischen Piloten und Drei-Strecken-Gesamtwertung](docs/media/demo.png)

[Echte Replay-Demo ansehen (WebM)](docs/media/demo.webm) · [Herkunft der Aufnahmen und synthetische Testdaten](docs/media/README.md). Echte Anwendungsaufnahmen, keine Mockups; kein Nachweis einer Release-Veröffentlichung oder Plattformabnahme.

## Schnellstart: Installation auswählen

Für beide Wege ist **Docker mit Compose** erforderlich: Docker Desktop mit **Linux-Containern** unter Windows/macOS oder Docker Engine mit Compose-Plugin unter Linux. Docker vorher starten. Bei Verwendung eines Archivs werden auf dem Host weder Python, Git, Node.js, npm noch uv benötigt. Der erste Download/Bau braucht Internet; mit vorhandenen Images läuft der Unterricht lokal ohne Cloud-Dienst oder CodinGame-Konto.

### Fertiges Release-ZIP — Veröffentlichung noch ausstehend

Für das erste Release **v1.0.0** ist **`Pod-Racing-Classroom-v1.0.0.zip`** unter [GitHub Releases](https://github.com/igathedub/pod-racing-classroom/releases) vorgesehen. **ZIP und Images erst als verfügbar betrachten, wenn das Release tatsächlich veröffentlicht ist.** GitHubs automatisch erzeugtes „Source code“-Archiv ist nicht das fertige Installationspaket. Bis dahin den Quellcode-Weg unten verwenden.

Nach Veröffentlichung:

1. Das genannte ZIP herunterladen und in einen neuen, eigenen Unterrichtsordner entpacken. Diesen Ordner für weitere Starts und Updates behalten.
2. Windows: **`Start.cmd`** doppelklicken. macOS: **`Start.command`** verwenden oder bei einer Sperre **`sh Start.sh`** im Terminal. Linux: **`sh Start.sh`**. Diese Helfer laden festgelegte App-/Bot-Images; sie bauen keinen Quellcode.
3. Auf Betriebsbereitschaft warten. **http://localhost:8765/teacher** öffnen und den **Teacher admin token** privat aus **`teacher-private.log`** in diesem Ordner lesen. Start speichert ihn mit nur für den Eigentümer geltenden Zugriffsrechten statt ihn auf der Konsole auszugeben. Datei/Token nicht projizieren, in Chats kopieren oder veröffentlichen.
4. Beamer: **http://localhost:8765/projector**. Lernendenansicht auf diesem Rechner: **http://localhost:8765/**.

Die `compose.yaml` des Release-ZIPs bindet `ghcr.io/igathedub/pod-racing-classroom-app@sha256:…` und `ghcr.io/igathedub/pod-racing-classroom-bot@sha256:…` an unveränderliche Multiarch-Digests, die aus den veröffentlichten **`v1.0.0`**-Tags aufgelöst werden, nicht an `:1.0.0` oder `latest`. Die Auslassungszeichen sind keine verwendbaren Image-Referenzen. Diese Anleitung behauptet **keinen geprüften anonymen Image-Download oder bereits erfolgte Veröffentlichung**. Neue Installationen nutzen das einzeilige **checkpoint-only**-Protokoll. `Stop.cmd` / `Stop.command` / `sh Stop.sh` stoppen das gespeicherte Projekt ohne Datenlöschung. Das Schließen des Startfensters allein stoppt die Container nicht.

Die ZIP-Starter speichern einen eindeutigen Projektnamen in **`.classroom-project`**; für jeden Neustart und jedes Update behalten. Sie ignorieren vorhandene `.env`-Dateien. Das ZIP legt **`127.0.0.1:8765`** in `compose.yaml` fest. Die folgenden `.env`-Einstellungen und einfachen Compose-Befehle gelten nur für Quellcodeinstallationen, nicht für das ZIP. Bei belegtem Port keinen fremden Dienst stoppen; Konflikt klären oder eine ausdrücklich konfigurierte Quellcodeinstallation verwenden.

### Aus öffentlichem Quellcode bauen — bereits möglich

Quellcodearchiv des öffentlichen Repositorys herunterladen und entpacken; alternativ mit vorhandenem Git klonen. Bis zur Veröffentlichung von v1.0.0 ist der geprüfte Anwendungsstand dieser Anleitung **`804ac8804dff8b29d0e1ccc4364bd29d0b46fdf2`**, kein veröffentlichtes Binärpaket.

**Nur für Quellcodeinstallationen:** Für eine **neue Installation** neben der Root-`compose.yaml` eine `.env` anlegen:

```dotenv
COMPOSE_PROJECT_NAME=pod-classroom-mein-workshop
POD_BOT_IMAGE=pod-classroom-bot:mein-workshop
POD_INPUT_PROTOCOL=checkpoint-only
POD_BIND=127.0.0.1
POD_PORT=8765
```

Jede unabhängige Quellcodeinstallation benötigt einen eigenen Projektnamen und einen eindeutigen lokalen `POD_BOT_IMAGE`-Tag, damit ihr Build kein Sandbox-Image einer anderen Klasse ersetzt. **Vorhandene Deployment-Konfiguration damit nicht überschreiben.** Ohne explizite Einstellung verwendet Source-Compose noch `legacy`. Das Beispiel wählt den neuen Einzeilen-Startcode; gespeicherte Bots werden nicht umgeschrieben.

- **Windows:** **`Docker-start.cmd`** doppelklicken.
- **macOS/Linux:** **`sh Docker-start.sh`** ausführen.

Diese vorhandenen Quellcode-Starter bauen App und Sandbox, warten auf Betriebsbereitschaft und zeigen lokale Logs. Anschließend die oben genannten URLs verwenden. Gleichwertige Befehle **nur für Quellcodeinstallationen** im Installationsordner:

```sh
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
docker compose logs classroom
```

Jede neue Dateninstallation erzeugt einen **eigenen zufälligen Lehrkraft-Schlüssel** und speichert ihn dauerhaft. Es gibt kein gemeinsames Standardpasswort. **Quellcodeinstallation:** Schlüssel in lokalen App-Logs mit `docker compose logs classroom` lesen. **ZIP:** Start speichert diese Logs privat in `teacher-private.log`. Niemals zur Schlüsselwiederherstellung Daten löschen oder ungeschwärzte Logs teilen.

## Unterricht durchführen

1. Vorab in einer **separaten leeren Demo-Installation** die sechs Beispiel-Bots hinzufügen, Qualifikation und Drei-Strecken-Finale testen. Niemals einen echten Klassenraum für einen Test zurücksetzen.
2. Unter `/teacher` die Programmierphase öffnen. Voreinstellung: **120 Minuten**; möglich sind **1–1440 ganze Minuten**. „Restzeit setzen“ zählt ab dem Klick. Die Abgabefrist ist nicht die Gültigkeitsdauer einer Einladung.
3. Lernende wählen einen Alias und fügen Python-Code ein oder laden eine Datei hoch. Änderungen bis zur Frist verwenden den privaten Besitzschlüssel desselben Browsers. Quellcode zusätzlich speichern; Besitzschlüssel und Lehrkraft-Schlüssel sind verschieden.
4. Abgabe schließen und Qualifikation starten. Dabei werden Quellcodeversionen eingefroren. Bis zu **100 Abgaben** sind möglich, nicht 100 gleichzeitig fahrende Pods.
5. Danach das Finale mit den besten **bis zu fünf** zugelassenen Bots starten; mindestens zwei sind nötig. Die Beameransicht projizieren, nicht die Zugangsdaten. **Finale gesamt** ist von den Positionen des gerade gezeigten Rennens getrennt.

Lehrkräfte können eine Abgabe nach Bestätigung löschen. Dabei werden **alle Replays mit diesem Bot**, auch gemeinsame Finalreplays, entfernt. Während laufender Rennen/Aufträge ist Löschen gesperrt. Es ist keine dauerhafte Personensperre.

## Regeln und Python-Schnittstelle

Neue Installationen senden **eine Eingabezeile pro Zug**, ohne Gegnerkoordinaten:

```text
x y checkpoint_x checkpoint_y distance relative_angle
```

Genau eine Aktionszeile ausgeben und flushen:

```text
target_x target_y thrust
```

Startcode und Regeln der **aktiven Installation** verwenden. Eine bestehende `legacy`-Installation sendet eine zweite Gegnerzeile; ein Protokollwechsel macht Programme inkompatibel, die sie weiterhin lesen. Die checkpoint-only-Nadja darf **keine Gegnerzeile** einlesen.

- Nur Python-Standardbibliothek. Dauerhafte Variablen außerhalb der Schleife halten. `print(..., flush=True)` verwenden; Debug-Ausgaben nach `sys.stderr`.
- Schub 0–100; größere/kleinere Ganzzahlen werden begrenzt. `BOOST` wirkt einmal je Rennen, danach wie Schub 100. `SHIELD` verhindert im Aktivierungszug und den folgenden zwei Zügen Schub; ohne Kollisionen hat es keine Schutzwirkung.
- Testläufe, Qualifikation und Finale laufen immer ohne Kollisionen. Pods können sich weder schieben noch blockieren.
- Alle Bots fahren dieselben drei Qualifikationsstrecken: Breiter Rundkurs (Wide Circuit), Fünf Kurven (Five Corners), Zickzackstrecke (Switchback). Disqualifizierte Bots kommen nicht ins Finale.
- Das Finale nutzt **Haarnadelkurs (Hairpin Run), Diamantrunde (Diamond Loop) und Technikrunde (Technical Loop)**. Die kleinste Summe der **drei ungerundeten Final-Zieleinlaufzeiten** gewinnt; Qualifikationszeiten zählen nicht. Es sind anteilige **simulierte Spielzüge, keine echten Sekunden**. Anzeigerundung ändert keine Platzierung.
- Nur wer alle drei Finalstrecken ohne Disqualifikation beendet, kann Gesamtsieger werden. Sonst DNF/DQ; ohne gültige Gesamtsumme gibt es keinen Champion. Bei exakt gleicher Summe entscheiden Alias ohne Groß-/Kleinschreibung, danach UUID.
- Die Lehrkraft kann die Gesamtwertung sofort sehen. Lernenden-/Beameransichten zeigen sie nach Ende des dritten aktuellen Finalreplays, wenn Serie und Auftrag abgeschlossen sind. Das ist Präsentationssteuerung, keine API-Geheimhaltung.

Details: [Drei-Strecken-Wertung](docs/three-track-final.md) · [Abgabefrist](docs/configurable-submission-time.md).

## Zuerst lokal; privates LAN nur bewusst freigeben

Standard ist **`127.0.0.1:8765`**, nur auf dem Gastgeber erreichbar. Diese Anleitung öffnet keine Firewall, legt keinen Tunnel an und ändert keine laufende Installation automatisch.

Für ein vertrauenswürdiges Unterrichts-LAN **nur bei einer Quellcodeinstallation** mit der Schul-IT abstimmen, dann in der `.env` **dieser Installation** ausdrücklich `POD_BIND=0.0.0.0` setzen und mit `docker compose up -d` neu erstellen. Die private LAN-IP des Hosts teilen, keine Docker-/VPN-Adresse. Firewall auf das private lokale Subnetz beschränken und mit zweitem Gerät testen; Gäste-WLAN kann Verbindungen sperren. Docker unter Linux kann manche Host-Firewall-Regeln umgehen: tatsächliche Erreichbarkeit prüfen. Zur Rückkehr `POD_BIND=127.0.0.1` setzen und neu erstellen. Bei belegtem Port `POD_PORT` ändern und URLs entsprechend anpassen.

Optionale Klasseneinladungen erlauben **100 Teilnahmesitzungen**, einschließlich Beamer-Browsern. Zeitlich begrenzte gemeinsame Codes und Cookies sind keine persönliche Identität oder missbrauchssichere Zulassung. Standardmäßige Secure-Cookies benötigen HTTPS. Einladungen und Ratenlimits machen **anonyme öffentliche Codeausführung nicht sicher**. Siehe [Sicherheit](SECURITY.md).

## Stoppen, neu starten und aktualisieren — Daten behalten

**ZIP:** Mit `Stop.cmd` / `Stop.command` / `sh Stop.sh` stoppen und mit `Start.cmd` / `Start.command` / `sh Start.sh` im **selben Ordner** fortsetzen; `.classroom-project` behalten. Keine einfachen `docker compose stop/start`-Befehle verwenden: Dabei fehlen gespeichertes Projekt, Defaults-Datei und Socket-Einrichtung.

**Nur Quellcode:** Im selben Installationsordner mit **demselben Compose-Projektnamen und derselben Konfiguration**:

```sh
docker compose stop
docker compose start
docker compose ps
```

Sitzungen, Quellcode, eingefrorene Abgaben, Replays und Lehrkraft-Schlüssel liegen im projektbezogenen Volume `classroom-data`, im Container unter `/data`. Bei Quellcodeinstallationen behält `docker compose down` das Volume; danach mit `docker compose up -d` starten. **`down --volumes`, Volume-Prune und Reset niemals als Update-/Reparaturschritt einsetzen.** Andere Quellcode-Ordner-/Projektnamen oder eine verlorene ZIP-`.classroom-project` können ein neues Volume auswählen und vorhandene Daten scheinbar verschwinden lassen.

Vor Updates laufende Aufträge beenden, Anwendung stoppen und vollständiges Datenvolume sowie Installationszustand privat sichern. **ZIP:** Release-Hinweise/Prüfsummen prüfen, das neuere verifizierte Release **über denselben Installationsordner entpacken**, `.classroom-project`, Datenvolume und Schlüssel behalten und mit dem Start-Helfer laden/starten. Keinen neuen Ordner verwenden oder die gespeicherte Projektdatei ersetzen. **Quellcode:** `.env`, Projektname, eindeutigen Bot-Image-Tag, Volume und Schlüssel behalten; nach Prüfung `docker compose up --build -d` verwenden. Eine bestehende Klasse nicht als Neuinstallation behandeln oder heimlich ihr Protokoll ändern. Unterbrochene Aufträge werden als fehlgeschlagen markiert, nicht fortgesetzt. Ein kopierter Quellcode-/ZIP-Ordner ist **kein Datenbackup**. Backups enthalten Schülercode und private Zugangsdaten.

## Sicherheitsgrenze

Nicht vertrauenswürdige Bots laufen **ausschließlich in eingeschränkten Docker-Containern**: ohne Netzwerk, Docker-Socket und Host-Mounts, als Nicht-root, mit schreibgeschütztem Dateisystem, verworfenen Capabilities sowie Ressourcen-/Ausgabelimits. Ohne Docker/Sandbox wird nicht ausgeführt; kein Host-Fallback.

**Die vertrauenswürdige App erhält den Docker-Socket: Das entspricht Host-Administratorrechten.** Ein read-only-Socket ist keine Grenze. Docker schützt nicht garantiert vor Kernel-/Runtime-Lücken. Dies ist ein lokales/vertrauenswürdiges LAN-Unterrichtswerkzeug, **kein fertiger anonymer Internetdienst**. Öffentlicher Betrieb braucht eine unabhängige Prüfung von Isolation, Zugang, HTTPS, Origin und Missbrauchsschutz. Docker aktuell halten; wirklich feindlichen Code nur auf einer isolierten entbehrlichen VM betreiben. [SECURITY.md](SECURITY.md) vor Bereitstellung lesen.

Bei Quellcodeinstallationen braucht Rootless Linux den tatsächlichen Socket in `POD_DOCKER_SOCKET` und einen Compose-Client am selben Daemon. Remote-Kontexte sind nicht der Standardfall; Ressourcenlimits hängen von cgroups ab. Socket-Pfade nicht raten, Windows-`npipe://` nicht in Linux-Container übernehmen.

## Leistung und Plattformnachweise

Ein berichteter vollständiger Lasttest auf einem **Windows-Desktop mit 16 logischen CPUs** verwendete 100 identische Nadja-Quellen und **100 logische HTTP-Clients**, nicht 100 gerenderte Browser:

| Messung | Beobachtung |
|---|---|
| 100 Abgaben | 0,645 s insgesamt; p95 571 ms |
| 300 Qualifikationsrennen | 858,436 s |
| Drei Finalrennen | 36,192 s |
| Archive | 303; kein DQ/DNF |
| Poll-Abfragen | 99.873; alle HTTP 200, keine Timeouts |
| Finale: Status-Antwortzeit | p95 3,327 s; Maximum 4,481 s |

Trotzdem wurden im Finale **511 Status- / 1.405 Replay-Ticks** und in der Qualifikation **2.100 Replay-Ticks** verpasst. Erfolgreiche HTTP-Antworten belegen **keine flüssige Wiedergabe in 100 Browsern**, feste Unterrichtsdauer oder öffentliche Hosting-Kapazität. Andere Bots/Hardware ändern Laufzeiten. Ältere Einzelfinal-Messungen in historischen Notizen beschreiben nicht den aktuellen Drei-Strecken-Ablauf.

| Plattform | Nachweis / Empfehlung |
|---|---|
| Windows + Docker Desktop, Linux-x86-64-Container | Echte Docker-Unterrichtsabläufe geprüft; obiger Lasttest auf Windows-Desktop. |
| macOS + Docker Desktop | Vorgesehener Weg; keine frische Hardwareinstallation dieses Releases geprüft. Vor Unterricht den vollständigen Demoablauf auf dem Ziel-Mac testen. |
| Natives Linux / ARM64 | Build-Unterstützung ist keine Hardwareabnahme. Tatsächlich veröffentlichte CI-/Image-Ergebnisse prüfen und Zielgerät manuell testen; Multiarch-Manifeste belegen keine native Ausführung. |

## Hilfe und Mitmachen

- **Docker nicht bereit/unhealthy:** Docker starten und Linux-Container wählen. ZIP: Start-Helfer erneut ausführen und Fehler lokal prüfen. Quellcode: `docker compose ps` und lokale `docker compose logs classroom` prüfen; Kontext und Socket müssen zusammenpassen.
- **Port belegt:** ZIP-Port 8765 ist fest; nur Quellcodeinstallationen können einen anderen `POD_PORT` wählen. Keinen fremden Dienst stoppen.
- **Daten scheinbar leer:** ursprünglichen Ordner und ZIP-`.classroom-project` beziehungsweise Quellcode-`.env` und Projektnamen prüfen. Nicht zurücksetzen oder neue Daten darüberlegen.
- **Schlüssel verloren:** ZIP: Start ausführen und `teacher-private.log` privat lesen; Quellcode: lokale Logs lesen. Nicht ungeschwärzt teilen oder das Volume löschen.

Für automatisierte Einrichtung: [sicherer KI-Prompt](docs/agent-setup.md). Reproduzierbare, nicht sicherheitskritische Probleme unter [GitHub Issues](https://github.com/igathedub/pod-racing-classroom/issues) melden; Schwachstellen gemäß [SECURITY.md](SECURITY.md). [Beiträge](CONTRIBUTING.md) sind willkommen. Originalcode: [MIT](LICENSE); Abhängigkeiten behalten ihre eigenen Lizenzen.
