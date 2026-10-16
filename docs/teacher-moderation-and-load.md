# Lehrkraft-Moderation und Lasttest mit 100 Abgaben

## Eine Abgabe löschen

In der **Lehrkraftansicht** den Teacher-Schlüssel verwenden. In **Abgegebene Bots** hat jede Abgabe eine eigene **Löschen**-Schaltfläche. Der Bestätigungsdialog nennt den Bot und die Auswirkungen; **Abbrechen** verändert nichts.

- Nur Lehrkräfte mit gültigem Schlüssel können löschen. Lernenden-/Beameransichten haben keine Löschbedienung; ein Besitzschlüssel reicht nicht für die API.
- Während Qualifikation, Finale oder privatem Testlauf ist Löschen serverseitig gesperrt. Die Bestätigung startet keinen Reset und kein neues Rennen.
- Entfernt werden Abgabe, Code/Besitzschlüssel, eingefrorene Teilnehmerreferenz und entsprechende Ranglistenzeile. Qualifikationsränge werden neu nummeriert; vor einem noch ausstehenden Finale rücken die nächsten geeigneten Bots nach. Ein bereits gefahrenes Finale wird nicht nachträglich neu besetzt.
- **Alle gespeicherten Replays mit diesem Bot werden ebenfalls entfernt, auch ein gemeinsames Finale.** Andere Abgaben und nicht betroffene Replay-Dateien bleiben unverändert. Ein betroffener Champion wird zurückgenommen, nicht automatisch durch einen erfundenen Sieger ersetzt.
- Ein dauerhafter Moderationszähler sorgt dafür, dass geöffnete Ansichten alte Replay-/Beamer- und Code-Caches verwerfen. Keine Garantie, bereits gesehene Namen aus Screenshots oder externen Browser-/Netzwerkaufzeichnungen zu entfernen.
- Das ist Löschen, **keine Namens- oder Teilnehmersperre**. In einer offenen Klasse sind neue Abgaben weiterhin möglich. Alte Besitzschlüssel können eine neu beanspruchte gleichnamige Abgabe nicht überschreiben.

API: `DELETE /api/admin/submissions/{UUID}` mit bestehendem Teacher-Header. Ohne Berechtigung 401, ungültige UUID 422, fehlende Abgabe 404, laufender Wettbewerb/Test oder unsicherer gespeicherter Bestand 409. Antwort enthält nur `deleted_id`, `removed_replays` und `moderation_revision`, keinen Code oder Besitzschlüssel.

## Daten- und Betriebsgrenzen

Die bestehende Single-Process-Architektur bleibt Voraussetzung. SQLite-Änderung, vorgelagerte Validierung und ein privates Recovery-Journal koppeln Replay-Staging an die bestätigte Moderationsrevision. Neustart stellt vor Commit verschobene Dateien wieder her oder entfernt nach Commit verbliebene Staging-Dateien. Ein Post-Commit-Cleanupfehler macht die bereits entfernten Archive nicht wieder öffentlich; Bereinigung wird beim Neustart/nächster Moderation erneut versucht.

Linux-Verzeichnisse und Journal-Dateien werden synchronisiert. Der native Windows-Host-Pfad überspringt dort nicht unterstütztes POSIX-Verzeichnis-fsync; dies ist keine native Windows-Stromausfall-Abnahme. Die echten Docker-Prüfungen verwenden Linux-Container. Bestehende private Backups können ältere Abgaben weiter enthalten und müssen entsprechend privat bleiben.

Ein Update löscht **keine** echte Abgabe automatisch und schaltet keine Website-/Klassensperre ein. Vor Backup-Rollout sichern und bestehenden Datenbestand vollständig vergleichen; Primär bleibt ein eigenes Deployment nach Freigabe.

## 100er-Grenze

Die begrenzte Kapazität steigt von 60 auf **100 Abgaben** und ebenso auf 100 authentifizierte Teilnahmesitzungen, falls das optionale Klassen-Gate verwendet wird. Bestehende IP-/Teilnehmer-Anfrageraten bleiben unverändert. Bei 100 Abgaben sind Updates mit dem eigenen Besitzschlüssel weiter möglich; eine neue 101. Abgabe wird abgewiesen.

100 Abgaben sind nicht 100 Pods gleichzeitig: Die Qualifikation fährt je Bot drei gemeinsame Kurse; das Finale nimmt weiterhin höchstens fünf Bots.

## Lasttest und Aussagegrenze

Der reale Test läuft in einer neuen, eigentumsmarkierten lokalen Docker-Instanz mit eigenem synthetischem Datenvolume, **ohne öffentliche Ports und ohne echte Unterrichtsdaten**. App-Limits: 4 CPUs, 1536 MiB, 256 PIDs. Standard-Ratenlimits bleiben aktiv.

Arbeitslast:

1. 100 eindeutige HTTP-Abgaben gleichzeitig aus einer 100-Worker-Barriere, mit echter Syntaxprüfung und Besitzschlüsseln.
2. Gleichzeitige Statusabfragen sowie anschließendes Rücklesen aller Quellen/IDs/Versionen und SQLite-Prüfung.
3. 100 parallele Updates mit den ursprünglichen Besitzschlüsseln, ohne fremde Übernahme.
4. 300 echte Docker-Qualifikationsrennen auf denselben drei Kursen, anschließend ein gleichzeitiges Fünfer-Finale und Rücklesen aller 301 Archive.
5. Im abschließenden Build zusätzlich gezieltes Löschen nach dem großen Wettbewerb, Integritätsvergleich der übrigen Daten und Neustartprüfung.

Dies ist **kein Test von 100 gleichzeitigen Chromium-Browsern**, keiner von 100 gleichzeitig ausgeführten Bots und keine Messung der öffentlichen Cloudflare-/Internetlatenz. Verwendet wird die gebündelte Nadja-Vorlage; bösartige/langsame Lernendenprogramme haben andere Laufzeiten. Der vertrauenswürdige HTTP-Generator läuft im Appcontainer: Cgroup-CPU/RAM enthalten auch dessen Aufwand und sind keine isolierte Servermessung. Peak-Werte sind Stichproben, keine garantierten Maxima.

Die unveränderte Vorversion wurde ebenfalls real mit 100 HTTP-Abgaben geprüft: **60 akzeptiert, 40 mit Kapazitätsfehler 409 abgewiesen**, keine 5xx/Transportfehler. Daher wurde nicht durch direkte SQLite-Einträge ein scheinbar erfolgreicher 100er-Test erzeugt.

## Nachgewiesene Ergebnisse des endgültigen Builds

- 100 gleichzeitige Abgaben: **100 × HTTP 200**, p50 **155,117 ms**, p95 **227,919 ms**, Maximum **234,604 ms**.
- 100 gleichzeitige Updates: **100 × HTTP 200**, p95 **222,929 ms**. IDs, Besitzschlüssel und gespeicherte Quellen vollständig rückgelesen.
- **300 echte Qualifikationsrennen in 134,809 s**, alle 100 Nadja-Bots beenden alle drei Kurse, keine Disqualifikationen. Fünfer-Finale **2,342 s**, gültiger Champion; alle **301 Replays** geprüft. Gesamter Controller-Lauf **144,202 s**.
- **Keine HTTP-5xx- oder Lastphasen-Transportfehler**. Live-Replay-Antworten p95 **11,511 ms** (lokale HTTP-Messung).
- Anschließend echte Moderation im großen Testbestand: **100 → 99 Abgaben**, **301 → 297 Replays**; gezielt drei Qualifikationen und das betroffene gemeinsame Finale entfernt. Löschantwort **569,751 ms**. Andere Abgaben/Replay-Dateien vollständig verglichen, Teacher-/Zugangs-/Sitzungs-/Jobdaten erhalten; Neustartprüfung bestanden.
- Alle eigentumsmarkierten synthetischen Testcontainer und -volumes danach entfernt und Nichtvorhandensein geprüft. Keine echten Unterrichtsdaten verändert.
- Unabhängige Code-Review ohne blockierende Befunde; zusätzlich Commit-Fehler nach Replay-Staging per Fault Injection geprüft. Python-/Chromium-Suite und Lint separat im PR-Bericht aufgeführt; lokale Ergebnisse sind kein gehosteter CI-Nachweis.

Die automatisierten Tests decken darüber hinaus Teacher-/Origin-Schutz, Sperre bei laufendem Test, Claims, Referenzbereinigung, unveränderte fremde Replays, Sondernamen wie `finished`/`Final`/`checkpoint-only`/`Reference ghost`, Unterbrechung vor/nach Commit sowie Root- und `/backup`-Ansichten ab. Mobile Chromium-Prüfung umfasst 100 sichtbare Listen-/Auswahl-Einträge ohne horizontales Überlaufen.
