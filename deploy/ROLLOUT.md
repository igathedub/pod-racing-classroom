# Ein Feature kontrolliert auf beide Server ausrollen

> **Betreiberverfahren, nicht ZIP-Schnellstart und keine Deploymentfreigabe.** [v1.0.0 ist veröffentlicht](../VERIFICATION.md), damit ist der Stand auf `codeweek-wi.de` aber nicht nachgewiesen. Vor jedem Eingriff tatsächlichen Bestand und ausdrücklich freigegebenen Ziel-SHA prüfen. Historischer Plan für `codeweek-classroom-v2`: [Archiv](../docs/history/codeweek-v2-rollout.md). Alte Freigaben/Übergabeprompts nicht als neuen Auftrag behandeln.

## Grundprinzip

**Ein freigegebener Quellstand, zwei unabhängige Deployments und Datenbestände.**

- Windows-Primärserver: `https://codeweek-wi.de/`, Root-Präfix.
- Mac-Reserve: `https://codeweek-wi.de/backup/`, eigenes Präfix und Volume.
- Gleicher Release-Commit und gleiche gewollte Feature-Einstellungen, aber eigene Images/Architekturen, Docker-Projekte, Volumes, Teacher-/Tunnel-Secrets und Cookies je Rolle.
- GitHub synchronisiert Code, **nicht** Abgaben, Replays oder laufende Container. `git pull` ist kein Deployment.

## Standardablauf

1. **Entwickeln:** Feature-Branch und PR, Tests/Review. Kein direktes Editieren laufender Container.
2. **Isoliert prüfen:** Native Docker-Sandbox, UI/API und bei Regel-/Protokolländerungen ein vollständiger synthetischer Wettbewerb mit eigenen Ressourcen.
3. **Auf Backup testen:** Private konsistente Sicherung, bestehende Daten/Zugänge erhalten, Kandidatenimage aus dem exakten PR-Commit. Keine Live-Qualifikation oder Klassenresets als Smoke-Test. Betreiber testet die öffentliche Backup-Ansicht.
4. **Freigeben:** Nach ausdrücklicher Betreiberfreigabe PR nach `main` zusammenführen. Release-Tag auf genau diesen Commit setzen, Ziel-SHA notieren. Tags nicht später auf andere Commits verschieben. Bei zusätzlichen Anwendungscodeänderungen nach der Abnahme erneut testen.
5. **Version festhalten:** Beide Hosts verwenden genau diesen Release-Commit, nicht unabhängig den jeweils neuesten `main`. Rolle und Architektur können unterschiedliche Images benötigen; Images je Rolle/Release eindeutig taggen und tatsächliche IDs festhalten. Wenn der Merge nur Betriebsdokumentation/Compose ändert, unveränderte App-Inputs gegen den getesteten Stand nachweisen.
6. **Primär kontrolliert aktualisieren:** Das dortige Hermes prüft aktiven Unterricht/Jobs, Bestand und private Konfiguration. Bei Aktivität stoppen und Wartungsfenster vereinbaren. Vorher privates Backup/Restore-Nachweis, danach nur die genehmigten Image-/Featureänderungen anwenden. Projekt/Volume, Keys, Cookie-/Tunnelrollen und bewusst deaktivierte Zugangsbarrieren unverändert lassen.
7. **Abnehmen:** Intern und öffentlich HTTP, Health/Sandbox, aktive Regeln, Editor/Download, Lehrkraft-/Projektorpfade und Browserkonsole prüfen. Vollständige Bestands-/Tokenprüfung, nicht nur Anzahl vergleichen. Keine Probeabgaben oder Wettbewerbe im echten Klassenraum.
8. **Dokumentieren:** Je Host Release-SHA, tatsächliche Image-ID, Featurewerte, Daten-/Zugangsprüfung und Rollbackziel privat festhalten. Erst dann beide Hosts als aktuell melden. Fehlende Windows-Rückmeldung bedeutet **Primär noch nicht nachgewiesen aktualisiert**.

Den konkreten Backup-/Restore-/Compose-Ablauf beschreibt [RESTORE.md](RESTORE.md). Bestehende private Overlays zuletzt anwenden; öffentliche geschützte Profil-Defaults dürfen einen absichtlich offenen Betrieb nicht versehentlich wieder sperren. Keine Secrets in Chat/Git oder ungefilterte Compose-/Inspect-Ausgaben.

## Zielstand und Kompatibilität

Für jeden genehmigten Rollout den exakten Quellcode-SHA beziehungsweise unveränderliche App-/Bot-Digests dokumentieren und gegen den tatsächlichen Bestand prüfen. Nicht ungefragt einen früheren Deployment-Tag, `latest` oder den neuesten `main` verwenden. Ein Quellcode-Fast-forward, grüner CI-Lauf oder veröffentlichtes v1.0.0-ZIP aktualisiert keinen vorhandenen Server.

Das Runtime-ZIP ist eine eigene lokale Installationsroute, kein Ersatz für bestehende private Compose-/Tunnelprofile. Beim Update vorhandenes Projekt, Volume, Teacher-/Claim-Keys, Zugangsschutz und absichtlich gesetzte Featurewerte erhalten. Protokollwechsel (`legacy` / `checkpoint-only`) separat abstimmen: Bots mit zusätzlicher Gegner-Eingabe werden nicht automatisch umgeschrieben. Keine neuen leeren Volumes als vermeintliche Reparatur starten.

## Rollback

Vorherige rollenbezogene Image-, Protokoll- und private Konfiguration wiederherstellen, kontrolliert neu erstellen und prüfen. Kein pauschaler Rückwechsel zu `legacy`: Ausgangszustand und seitdem abgegebene Bots berücksichtigen. Keine Rücksicherung über neuere Abgaben; bei inkompatibler Datenmigration nur ein separat restauriertes Volume nach Freigabe anbinden. [Restore-Verfahren](RESTORE.md) und aktueller privater Betreiberbericht bestimmen den konkreten Rückweg.
