# Ein Feature kontrolliert auf beide Server ausrollen

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

## Aktuelles Feature: Nadja und Einzeilen-Protokoll

Vorgesehener Release-Tag: **`codeweek-checkpoint-v1`**. Vor Deployment auflösen und Ziel-SHA berichten:

```text
git status --short
git fetch origin --tags
git rev-parse codeweek-checkpoint-v1^{commit}
```

Bei lokalen Änderungen oder einem bereits vorhandenen, abweichenden Tag stoppen. Einen sauberen Release-Checkout/Worktree auf dem aufgelösten Commit verwenden; keine bestehenden Änderungen überschreiben. Der laufende Container bleibt bis zum geplanten Deployment unverändert.

In der **bestehenden privaten** Deployment-Env je Host:

```dotenv
POD_INPUT_PROTOCOL=checkpoint-only
```

Die Basis-Compose-Datei reicht diese Variable an `classroom` weiter. Ohne Variable bleibt `legacy` aktiv; explizit leer/ungültig wird an die App weitergereicht und dort vor Datenerzeugung abgewiesen. Ein späteres privates Overlay kann den Wert überschreiben: effektiven Wert ohne Secrets prüfen und nach dem Recreate im tatsächlichen Appcontainer bestätigen. Nur `.env` ändern oder `docker restart` reicht nicht, um die Container-Umgebung zu ersetzen.

Die aktive Einstellung ist öffentlich unter `/api/rules` bzw. `/backup/api/rules` an `protocol.name == "checkpoint-only"` und genau einer Eingabezeile prüfbar. Starter und Download müssen zur neuen Nadja-Datei passen. Herkunft, Syntaxkorrektur und Testergebnisse: [checkpoint-only-backup.md](../docs/checkpoint-only-backup.md).

**Breaking Change:** Alte Bots mit einer zweiten Gegner-`input()`-Zeile müssen vor der nächsten Qualifikation angepasst werden. Kein automatisches Umschreiben oder Löschen alter Abgaben. Alte Replay-Dateien bleiben unverändert. Physik, Sandbox und Teacher-Rechte werden durch diese Freigabe nicht geändert.

### Übergabeprompt für das Hermes auf Windows

> Rolle: bestehender Windows-Primärserver für `https://codeweek-wi.de/`. Der Betreiber hat das auf Backup getestete Nadja-/Einzeilen-Feature zum Rollout freigegeben. Lies `deploy/ROLLOUT.md`, `deploy/RESTORE.md` und `docs/checkpoint-only-backup.md` aus `igathedub/pod-racing-classroom`. Hole den Release-Tag `codeweek-checkpoint-v1`, löse ihn zu einem Commit auf und verwende genau diesen Stand, nicht einfach einen späteren main. Prüfe zuerst Git-Änderungen, tatsächlichen lokalen Docker-Kontext/Endpunkt, bestehendes Projekt, App-/Bot-/Gate-Images, Datenvolume, private Overlays, Unterrichts-/Jobstatus und aktuellen Zugangsschutz. Keine Neustarts bei aktivem Unterricht/Job. Erzeuge und prüfe vorher eine private konsistente Sicherung samt passenden Operator-/Tunneldateien und einen isolierten Restore-Nachweis. Baue/prüfe das passende rollengetrennte Appimage; bewahre sämtliche Daten, Teacher-/Claim-Keys, Windows-Tunnel und die bestehenden Auth-Einstellungen. Aktiviere `POD_INPUT_PROTOCOL=checkpoint-only` im tatsächlichen Appcontainer über die bestehende private Compose-Konfiguration. Bestehende Website-/Klassensperren nicht wieder einschalten; kein Reset, keine Migration alter Botquellen, kein neues leeres Volume und kein Pruning. Prüfe neues Image und Rules/Editor/Download öffentlich sowie lokal, vollständigen Daten-/Token-Erhalt, Lehrkraft-/Projektoransicht und Browserfehler. Bei Fehlern altes Appimage und alten Protokollwert kontrolliert zurücknehmen, ohne neuere Daten zu überschreiben. Berichte danach Release-SHA, tatsächliche App-/Bot-Image-IDs, aktives Protokoll, Tests, Daten-/Zugangserhalt und etwaige Blocker getrennt. Keine Credentials oder Lernendencodes im Bericht.

## Rollback

Vorherige rollenbezogene Image- und Protokollkonfiguration wiederherstellen, dann kontrolliert neu erstellen und prüfen. Hier ist das alte Protokoll `legacy`. Keine Rücksicherung über neuere Abgaben; bei inkompatibler Datenmigration nur ein separat restauriertes Volume nach Freigabe anbinden. Neu geschriebene Einzeilen-Bots sind umgekehrt nicht automatisch legacy-kompatibel. Deshalb auch den Rückweg vor der nächsten echten Qualifikation mit der Lehrkraft abstimmen.
