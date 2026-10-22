# Primär-Hermes: geprüften Backup-Funktionsstand übernehmen

## Auftrag und exakter Zielstand

Aktualisiere den **bestehenden Windows-Primärserver** von Pod Racing Classroom auf den geprüften Backup-Funktionsstand. Arbeite autonom bis zur verifizierten Fertigstellung, innerhalb der unten beschriebenen Sicherheitsgrenzen.

- Repository: https://github.com/igathedub/pod-racing-classroom.git
- Quellbranch: `feat/three-track-final`
- **Exakter freigegebener Anwendungscommit: `804ac8804dff8b29d0e1ccc4364bd29d0b46fdf2`**
- Öffentlicher Primär-Einstieg: `https://codeweek-wi.de/`, ohne `/backup`-Präfix.

Verwende exakt diesen Anwendungscommit in einem sauberen Release-Worktree. Ein `git pull` auf `main` reicht nicht: Der freigegebene Stand liegt auf dem Featurebranch. Keine automatischen PR-Merges erforderlich. Der Dokumentationscommit, der dieses Handoff hinzufügt, ist **nicht** ein neues Anwendungsziel; die oben genannte SHA bleibt maßgeblich.

Auf Backup wurden 519 Tests bestanden (48 opt-in Tests übersprungen), unabhängige Reviews und eine native Docker-Abnahme einschließlich Neustart ausgeführt. Das ist keine Behauptung über bereits ausgeführte Windows- oder Primärprüfungen.

## Vollständiger Funktionsumfang

- Neue Nadja-Vorlage und `checkpoint-only`-Eingabeprotokoll.
- Maximal 100 Abgaben und geschützte Lehrkraft-Löschung.
- Variable Abgabezeit von 1–1440 ganzen Minuten.
- Kollisionsfreie Testläufe, Qualifikation und Finale.
- Qualifikation auf drei bisherigen gemeinsamen Strecken.
- Finale mit denselben bis zu fünf qualifizierten Bots auf drei **anderen** Strecken: Hairpin Run, Diamond Loop und Technical Loop.
- Gesamtsieger nach kleinster Summe der drei gültigen, ungerundeten **simulierten Finalzeiten**. Qualifikationszeiten zählen nicht mit. Alle drei Finalstrecken müssen ohne Disqualifikation beendet werden. Ohne gültige Gesamtsumme kein Gesamtsieger; bei exaktem Gleichstand entscheiden Alias ohne Beachtung der Großschreibung und dann UUID.
- Ansicht „Finale gesamt“ mit Einzel- und Gesamtzeiten.
- Korrekt verzögerte Siegeranzeige und rechtsbündige Zahlenüberschriften in allen drei Ranglistentabellen.

## 1. Bestand und Wartungsfenster prüfen

Zuerst nur lesend den tatsächlichen Git-/Docker-Zustand, Linux-Containerbetrieb, bestehendes Compose-Projekt, Datenvolume, App-/Bot-/Gate-Images, private Overlays sowie Unterrichts-/Jobstatus ermitteln. Keine Namen oder Windows-Pfade aus Mac-Beispielen übernehmen. Lokale Änderungen nicht überschreiben oder automatisch stashen.

Bei offener Abgabephase oder laufendem Wettbewerb **nicht** neu starten, schließen oder zurücksetzen. Dann mit konkretem Blocker und benötigtem Wartungsfenster zurückmelden.

## 2. Private Sicherung und Wiederherstellungsnachweis

Vor dem Deployment ein privates konsistentes Backup einschließlich Betreiber-/Tunnelkonfiguration erzeugen, Integrität prüfen und einen isolierten Restore-Nachweis durchführen. Dateirechte unter Windows korrekt prüfen; keine Sicherheitsprüfungen umgehen.

## 3. Strikte Daten- und Rollentrennung

Ausschließlich Primär-Code und gewünschte Featurewerte aktualisieren. Bestehende Primär-Abgaben, Botquellen, Claim-Schlüssel, Replays, Ranglisten, Teacher-Token und Cloudflare-Tunnel erhalten.

- Keine Backup-Daten, Backup-Secrets oder Mac-Images übernehmen.
- Kein Reset, kein leeres Ersatzvolume, kein Pruning, kein `down -v`.
- Historische Ergebnisse weder neu berechnen noch umschreiben.

## 4. Absichtlich gesetzte Zugangseinstellungen

Die effektive Primär-Konfiguration muss enthalten:

```dotenv
POD_BASE_PATH=
POD_INPUT_PROTOCOL=checkpoint-only
POD_CLASS_ACCESS_REQUIRED=0
```

Website-Benutzername/Passwort-Sperre und Klasseneinladung bleiben **aus** und dürfen nicht wieder eingeschaltet werden. Teacher-Token-Schutz bleibt **ein**.

**Achtung:** `deploy/compose.codeweek-primary.yaml` enthält geschützte Beispielwerte. Nicht ungeprüft übernehmen! Bestehende private Overrides zuletzt anwenden und effektive Werte kontrollieren. Ältere Abschnitte in `deploy/ROLLOUT.md` zu `codeweek-classroom-v2` ersetzen nicht den hier genannten aktuellen Zielcommit.

## 5. Rollenrichtige Images und echte Bereitschaft

Rollenrichtige Windows-/Linux-Container-Images aus dem Zielcommit bauen. App und Bot müssen zur tatsächlichen Primär-Konfiguration passen. Den Mac-spezifischen `Dockerfile.local` und dessen Bot-Image-Namen **nicht** übernehmen.

Tatsächlichen Kaltstart und Container-Healthcheck mit den späteren Produktionseinstellungen testen. Test-Overrides dürfen fehlende Image-Konfiguration nicht verdecken.

## 6. Isolierte Abnahme vor Aktivierung

Vor Aktivierung isoliert prüfen:

- Testsuite und echte Docker-Bots.
- Drei Qualifikations- und drei andere Finalstrecken.
- Aus den tatsächlichen Replays rekonstruierte Finalzeitsummen und korrekter Gesamtsieger, auch wenn er nicht das letzte Einzelrennen gewinnt.
- Kollisionsfreiheit, Neustartbeständigkeit und die drei Tabellen.

Keine Testabgaben, Löschtests oder Wettbewerbe im echten Klassenraum.

## 7. Kontrolliertes Deployment und Rollback

Kontrolliert auf dem bestehenden Projekt/Volume deployen. Vor Wiederöffnung des Zugangs vollständige gespeicherte Daten und Replay-Dateien mit dem Vorabstand vergleichen, **nicht nur Zählwerte**. Teacher-/Claim-Schlüssel intern vergleichen, niemals ausgeben.

Bei Fehlern das alte Image und die alte Konfiguration wiederherstellen, ohne neuere Unterrichtsdaten zu überschreiben.

## 8. Lokale und öffentliche Nachprüfung

Danach lokal und öffentlich prüfen:

- `/api/health`, `/api/rules`, `/teacher` und `/projector`.
- `checkpoint-only`, Limit 100, variable Abgabezeit und neue Finalregeln.
- Tabellenüberschriften und Browserkonsole.

Keine Credentials, Lernendencodes oder ungefilterten Docker-Inspect-/Compose-Ausgaben in Chat oder Logs veröffentlichen.

## Referenzen und Abschlussbericht

Lies `deploy/RESTORE.md`, `deploy/ROLLOUT.md` und die Feature-Dokumente unter `docs/` aus dem Zielstand, insbesondere:

- `docs/checkpoint-only-backup.md`
- `docs/teacher-moderation-and-load.md`
- `docs/configurable-submission-time.md`
- `docs/collision-free-racing.md`
- `docs/three-track-final.md`

Dieses Handoff definiert den aktuellen Zielcommit und die ausdrücklich offenen Zugangseinstellungen; historische geschützte Beispielprofile sind keine Anweisung, die Sperren wieder einzuschalten.

Berichte abschließend den tatsächlichen Quellcommit, App-/Bot-Image-IDs, Health- und öffentliche Prüfergebnisse, vollständigen Daten-/Zugangserhalt, Rollbackziel und gegebenenfalls verbleibende Blocker.

**„Fertig“ erst melden, wenn der laufende Primärcontainer und die öffentlichen Ansichten nachweislich aktualisiert sind.**
