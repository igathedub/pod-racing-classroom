# Pod Racing Classroom

**Python-Bots. Faire Qualifikation. Ein Klassenfinale auf drei Strecken.**

Entwickelt für die **Codeweek 2026 in Wiesbaden**. Lernende brauchen einen Browser; die Lehrkraft betreibt Docker. Deutsche/englische Lernenden-, Lehrkraft- und Beameransichten mit privaten Testläufen und animierten Replays. Ein eigenständiges, von CodinGame inspiriertes Spiel, kein offizieller Referee oder verbundenes Produkt; ein Pod je Person, kein Gold-Liga-Teamspiel.

[English](README.md) · [Dokumentation](docs/README.md) · [Sicherheit](SECURITY.md) · [Mitmachen](CONTRIBUTING.md) · [MIT-Lizenz](LICENSE)

## v1.0.0 starten

**Docker mit Compose v2** muss laufen: Docker Desktop mit **Linux-Containern** unter Windows/macOS oder Docker Engine mit Compose-Plugin unter Linux. **Kein Host-Python, Git, Node.js, npm oder uv nötig.** Der erste Start lädt Images und braucht Internet; danach läuft der Unterricht lokal.

1. [**Pod-Racing-Classroom-v1.0.0.zip**](https://github.com/igathedub/pod-racing-classroom/releases/download/v1.0.0/Pod-Racing-Classroom-v1.0.0.zip) aus dem [veröffentlichten stabilen Release](https://github.com/igathedub/pod-racing-classroom/releases/tag/v1.0.0) herunterladen, mit [SHA256SUMS](https://github.com/igathedub/pod-racing-classroom/releases/download/v1.0.0/SHA256SUMS) prüfen und in einen neuen, eigenen beschreibbaren Ordner entpacken. Dieses Asset verwenden, **nicht** GitHubs automatisches „Source code“-Archiv oder das historische reine Quellcode-Release `v1.0.0-preview.1`.
2. **Windows:** `Start.cmd` doppelklicken. **macOS:** `Start.command` oder bei einer Sperre `sh Start.sh` im Terminal. **Linux:** `sh Start.sh`. Die Starter laden festgelegte App-/Bot-Images, ohne Quellcode zu bauen.
3. Auf Betriebsbereitschaft warten. **http://localhost:8765/teacher** öffnen und den **Teacher admin token** privat aus **`teacher-private.log`** im Ordner lesen. Der Schlüssel wird lokal erzeugt und mit Eigentümerrechten gespeichert, nicht auf der Starter-Konsole ausgegeben. Datei/Token niemals teilen oder projizieren.
4. Lernendenansicht: **http://localhost:8765/**. Beamer: **http://localhost:8765/projector**. Diese URLs gelten **nur auf diesem Rechner**; das ZIP legt `127.0.0.1:8765` fest, ignoriert vorhandene `.env` und öffnet weder Firewall noch Tunnel oder LAN-Zugang.

Bei belegtem Port 8765 keinen fremden Dienst stoppen. Konflikt klären oder bewusst eine [Quellcodeinstallation](docs/source-installation.md) konfigurieren. Prüfsummenbefehle, feste Image-Digests und Plattformgrenzen stehen unter [Verifikation](VERIFICATION.md); für Automatisierung gibt es den [sicheren KI-Prompt](docs/agent-setup.md).

## Erst die Demo, dann unterrichten

In dieser **neuen leeren Demo-Installation** über die Lehrkraftansicht sechs Beispiel-Bots hinzufügen, Qualifikation und Drei-Strecken-Finale starten: **18 Qualifikationsrennen + 3 Finalrennen = 21 Replays**. Beameransicht projizieren, keine Zugangsdaten. Niemals eine echte Klasse für die Demo zurücksetzen. Vor dem Unterricht den vollständigen Ablauf auf dem Zielgerät prüfen, besonders bei macOS/ARM64.

![Echte Beameransicht mit synthetischen Piloten und Drei-Strecken-Wertung](docs/media/demo.png)

[Replay-Demo ansehen (WebM)](docs/media/demo.webm) · [Herkunft der Aufnahmen](docs/media/README.md). Echte Anwendung mit synthetischen Piloten, keine Plattformzertifizierung.

1. Unter `/teacher` die Programmierphase öffnen: **120 Minuten** voreingestellt, **1–1440 ganze Minuten** möglich. „Restzeit setzen“ zählt ab dem Klick; Einladungsgültigkeit ist getrennt.
2. Lernende wählen einen Alias und nutzen **„Deinen Bot abgeben“** für eingefügten oder hochgeladenen Python-Code. Der private Besitzschlüssel desselben Browsers erlaubt Änderungen bis zur Frist. Quellcode zusätzlich speichern; Besitzschlüssel und Lehrkraft-Schlüssel sind verschieden. Private Testläufe gehen nicht in den Wettbewerb ein.
3. Abgabe schließen und Qualifikation starten; Quellcodeversionen werden eingefroren. Bis zu **100 Abgaben**, nicht 100 gleichzeitig fahrende Pods.
4. Finale starten: die besten **bis zu fünf** zugelassenen Bots, mindestens zwei nötig. **Finale gesamt** ist von den aktuellen Rennplatzierungen getrennt. Die Replay-Steuerung zeigt **„Automatisch folgen: AN“** oder **„Automatisch folgen: AUS“**.

Lehrkraft-Löschung braucht Bestätigung, ist während laufender Rennen/Aufträge gesperrt und entfernt **alle Replays mit diesem Bot**, auch gemeinsame Finalreplays. Keine dauerhafte Personensperre.

## Regeln und Python-Schnittstelle

Neue Release-ZIP-Installationen senden **eine Eingabezeile pro Zug**, ohne Gegnerkoordinaten:

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

## Stoppen, neu starten, aktualisieren — Daten behalten

- **Stoppen:** `Stop.cmd` / `Stop.command` / `sh Stop.sh`. **Fortsetzen:** passender Start-Helfer im **selben Ordner**. Fensterschließen stoppt keine Hintergrundcontainer. Beim ZIP keine einfachen `docker compose stop/start`-Befehle: gespeichertes Projekt, Defaults und Socket-Einrichtung würden fehlen.
- **`.classroom-project` behalten**: Die Datei identifiziert das projektbezogene Volume `classroom-data` (`/data`) mit Sitzung, Quellcode, eingefrorenen Abgaben, Replays und Lehrkraft-Schlüssel. Ein neuer Ordner/Projektname kann Daten scheinbar verschwinden lassen. Keine zwei Kopien mit derselben Projektdatei betreiben.
- Vor Updates Aufträge beenden, stoppen und **vollständiges Datenvolume samt Installationszustand** privat sichern. Der kopierte ZIP-Ordner ist **kein Datenbackup**. Release-Hinweise/Prüfsummen prüfen; neueres verifiziertes ZIP **über denselben Ordner** entpacken, `.classroom-project`, Volume und Schlüssel behalten, dann Start verwenden. Kein Reset, Volume-Prune oder `down --volumes` zur Aktualisierung/Reparatur. Unterbrochene Aufträge werden nicht fortgesetzt.

## Sicherheit und Plattformnachweise

Bots laufen nur in eingeschränkten Docker-Containern: ohne Netzwerk, Docker-Socket oder Host-Mounts, als Nicht-root, mit schreibgeschütztem Dateisystem, verworfenen Capabilities sowie Ressourcen-/Ausgabelimits. Ohne Sandbox keine Ausführung und kein Host-Fallback. **Der Docker-Socket der vertrauenswürdigen App entspricht Host-Adminrechten**; Docker garantiert keinen Schutz vor Kernel-/Runtime-Lücken. Öffentlicher Quellcode ist **keine Freigabe für anonyme Internet-Codeausführung**. [SECURITY.md](SECURITY.md) lesen; wirklich feindlicher Code benötigt unabhängig geprüfte Isolation, etwa eine entbehrliche eigene VM.

Release-ZIP und öffentliche Linux-AMD64-Images sind geprüft; Windows Docker Desktop hat den vollständigen Demoablauf samt Neustart durchlaufen. Native Linux-AMD64-/ARM64-**Quellcode-Build-CI** ist von der Ausführung veröffentlichter Images zu unterscheiden. Keine native Mac-Docker-Abnahme und keine Ausführung veröffentlichter ARM64-Images behauptet. [Aktuelle Verifikation](VERIFICATION.md) und [berichtete Lastmessungen](docs/performance.md) trennen die Nachweise; 100 logische Clients sind keine 100 flüssig gerenderten Browser.

## Hilfe und fortgeschrittene Einrichtung

- **Docker nicht bereit/unhealthy:** Docker mit Linux-Containern starten, Start erneut ausführen und Fehler lokal prüfen.
- **Daten scheinbar leer:** ursprünglichen Ordner und `.classroom-project` prüfen; nicht zurücksetzen oder neue Daten darüberlegen.
- **Lehrkraft-Schlüssel verloren:** Start ausführen und `teacher-private.log` privat lesen. Kein gemeinsames Standardpasswort; niemals Volume löschen oder ungeschwärzte Logs teilen.
- [Quellcode-Builds, vertrauenswürdiges LAN und Rootless-Konfiguration](docs/source-installation.md) sind bewusste fortgeschrittene Alternativen, keine ZIP-`.env`-Einstellungen. Diese Anleitung führt kein LAN-/Internet-Deployment aus.
- [Dokumentationsindex](docs/README.md) · [Mitmachen](CONTRIBUTING.md) · [GitHub Issues](https://github.com/igathedub/pod-racing-classroom/issues). Schwachstellen gemäß [SECURITY.md](SECURITY.md) melden. Originalcode: [MIT](LICENSE); Abhängigkeiten behalten ihre Lizenzen.
