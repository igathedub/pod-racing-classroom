# Native Windows-Abnahme: ACL und privater Restore

Nachweisstand: 15. Oktober 2026. Repository-Basis `e10c9c27640c6cb5789d6e35812ce4f1136029b2` (PR #9), mit den begleitenden Windows-Korrekturen dieser Änderung. **Keine Produktivaktualisierung oder Tunnel-/DNS-Änderung.**

## Repository-Neuerungen

- PR #8: Primär-/Reserve-Compose-Profile, `/backup`-Basispfad, unabhängiger Mac-Tunnel/Edge-Worker, private Backup-/Restore-CLI.
- PR #9: ausführbarer CLI-Einstieg, SID-basierte ACL-Prüfung, echte Prozess- und Docker-Abnahmetests, korrigierte Wiederherstellungsanleitung.
- Die bisherigen Mac-Abnahmen belegten ausdrücklich weder native Windows-ACLs noch einen Restore des privaten Windows-Unterrichtsbestands. Diese Lücke wurde hier auf dem Windows-Primärhost geprüft.

## Zwei erst nativ sichtbare Blocker

1. **Owner-Rights-ACL:** natives `mkdir(mode=0700)` erzeugt unter den hier eingesetzten Python-Versionen eine ACL mit `S-1-3-4`. Der Prüfer lehnte diese trotz korrektem Eigentümer ab. Microsoft definiert OWNER RIGHTS als die Gruppe, die den aktuellen Eigentümer des Objekts repräsentiert.[1] Die Korrektur erlaubt diese SID **erst nach unverändertem Vergleich Eigentümer-SID = Betreiber-SID**. Everyone, lokale Users und fremde Eigentümer bleiben verboten.
2. **Offener SQLite-Handle:** `with sqlite3.connect(...)` schließt die Verbindung nicht beim Verlassen. Der Snapshotleser hielt die Datei bis zur Garbage Collection offen; unter Windows schlug das Löschen des Restore-Audit-Tempverzeichnisses fehl. Der Leser verwendet jetzt `contextlib.closing`. Sein Sourcecode wird weiterhin mit allen benötigten Imports in den vertrauenswürdigen Container übertragen.

TDD-Nachweise: Owner-Rights-Regressionslauf zunächst **2 failed, 3 passed**, danach 5 passed. Separater nativer Dateifreigabetest zunächst **WinError 32**, danach bestanden. Aktuelle neue Regressionsdatei: **6 passed**.

Die alten Mocktests hatten zusätzlich POSIX-Dateimodus-Annahmen und verwechselten `C:`-Hostpfade mit Containerpfaden. Die Mockgrenze erkennt jetzt nur bekannte Container-IDs; Windows prüft echte ACLs statt Unix-Modusbits. Die POSIX-Writable-Parent-Prüfung bleibt für POSIX erhalten und ist auf Windows ausdrücklich übersprungen. Mock-Backup-Locks sind in eigenen Testverzeichnissen statt im Betreiber-Home isoliert.

## Native ACL-Nachweise

Die Windows-PowerShell-/Get-Acl-Prüfung wurde ohne Mock durchgeführt:

- Korrekt betreibereigenes Verzeichnis: akzeptiert.
- Zusätzliche Everyone-Allow-ACE: abgelehnt.
- Fremder Eigentümer: abgelehnt.
- Geerbte Everyone-Allow-ACE: abgelehnt.
- Natives `mkdir(0700)` mit OWNER RIGHTS: nach Korrektur akzeptiert.
- Vorhandenes privates Operator-Verzeichnis: **10 Objekte geprüft, keine Eigentümer-/Allow-ACE-Verstöße**.
- Privates Ausgangsbackup: **68 Objekte geprüft, keine Eigentümer-/Allow-ACE-Verstöße**.
- Die vier positiven/negativen ACL-Fälle wurden nach der Korrektur erneut nativ geprüft.

Bestehende private Operator-/Backup-ACLs wurden nicht verändert. Nur neue, ausschließlich synthetische ACL-Testfixtures erhielten explizite Test-ACLs.

## Tatsächlicher Restore des privaten Unterrichtsbestands

Ausgangssnapshot: privates Backup `2026-10-14_193335`; keine synthetisch erfundenen Unterrichtsdaten. Archiv und vorhandene Snapshotkopie wurden für **62 Dateien bytegenau verglichen**. Snapshotinhalt: **20 Abgaben, 61 Replays/Replay-Dateien**, Sitzung und Job finished.

Abnahme auf dem bestätigten lokalen Docker-Endpunkt `desktop-linux` / `npipe:////./pipe/dockerDesktopLinuxEngine`:

1. Separates Appimage aus dem aktuellen Repository-Dockerfile gebaut: Tag `pod-classroom-windows-proof:e10c9c2-native`; keine Produktiv- oder Standard-Image-Tags überschrieben.
2. Privaten Snapshot in ein neu gelabeltes Testvolume kopiert; Test-App ohne Netzwerk, Hostports oder Docker-Socket gestartet. Keine fremden Botprogramme ausgeführt.
3. Echte Cold-Backup-Funktion an dieser Test-App mit eigenem Lock-Namespace ausgeführt. Nur Test-App und Test-Gate wurden gestoppt/gestartet; originale Test-Container-ID/Image/Config und Gate-Resumption verglichen. Dieser Schritt ist ein Funktionsaufruf, kein als direkter CLI-Backup-Prozess ausgegebener Nachweis.
4. Vier vorhandene private Operator-Dateien mitgesichert und bytegleich verglichen; keine Werte oder Hashes ausgegeben.
5. **Echten `check`-CLI-Prozess** ausgeführt: status verified, 20/61.
6. **Echten `restore`-CLI-Prozess** in ein garantiert neues Volume ausgeführt: 20/61. CLI-Ausgabe für session/job ist dort null, weil restore diese Felder nicht liefert; die Sitzung/Job-Werte wurden separat durch Datenbank-/Snapshotvergleich belegt.
7. Restauriertes Volume vor Appstart unabhängig zurückkopiert: **sämtliche Daten-Dateien bytegleich, alle SQLite-Tabellenzeilen unverändert**, einschließlich Teacher-Token, Abgabeschlüsseln und Klassen-/Sitzungsdaten. Diese Werte wurden nicht ausgegeben.
8. Wiederholter Restore in dasselbe vorhandene Volume korrekt abgelehnt.
9. Restaurierte Anwendung gestartet: gesund; intern mit dem aus der restaurierten Datenbank gelesenen bestehenden Teacher-Token `/api/state` → **HTTP 200, 20 Abgaben**. Separater Start mit **`/backup`** ebenfalls gesund.
10. Erfolgreiche Testcontainer/-volumes anhand beobachteter IDs/Labels entfernt und Entfernung zurückgelesen. Keine Cleanup-Fehler im erfolgreichen Lauf. Die zuvor fehlgeschlagenen Restore-Volumes bleiben gemäß CLI-Vertrag zur privaten Diagnose erhalten; daraus wird kein globaler Nachweis „keine Testressourcen vorhanden“ abgeleitet.

## Unveränderter Produktivbetrieb

Vorher/nachher wurde der Windows-Primärbestand verglichen:

- Originale App- und Gate-Container-IDs, Images und Konfigurationen unverändert; beide laufen.
- App weiterhin healthy, keine App-Hostports; Originaldatenvolume unverändert.
- Originales Appimage: `sha256:253b1a50cfc85a2c406cb03d224dbeb14a45cc59bccbdf34ad8c01a3a82c4300`.
- **20 Abgaben, 61 Replays und sichere Snapshot-Status-/Zählfelder unverändert.**
- Keine Produktivcontainer für den Nachweis gestoppt, keine Live-Abgaben/Rennen erzeugt, keine Tunnel/DNS/Secrets/Studentenfreigabe geändert.

## Weitere Prüfungen und klare Grenzen

- Gesamter Nicht-Docker-Python-Lauf auf Windows: **267 passed, 2 skipped, 31 deselected**, 188 Sekunden. Kein Nachweis ausgeführter Hosted-CI.
- Worker: **11 Node-Tests bestanden**.
- Added-Line-Sicherheitsprüfung: keine realen Secrets, Shell-Injection, eval/exec oder unsichere Deserialisierung gefunden.
- Read-only öffentliche Probes von diesem Windows-Host lieferten **403 mit Server cloudflare** für Root, `/backup/` und technischen Origin. Das ist kein erfolgreicher 401-/Passwortnachweis und widerspricht einer pauschalen Übernahme älterer Mac-Probes. Ursache dieses 403 und externe autorisierte HTTPS-Abnahme sind hier nicht geklärt.
- Kein Fernzugriff auf den Mac durchgeführt; kein Restore seines eigenständigen Unterrichtsbestands behauptet.
- Ausgangspunkt war ein vorhandener geprüfter Windows-Snapshot, kein frisch gestoppter Produktivserver. Damit ist nicht die Aktualität einer vollständigen neuen Produktivsicherung bewiesen.
- Daten-/Operator-Restore belegt, nicht vollständiger Hardwareausfall-Restore: Imagearchiv, sämtliche Tunnel-Credentials, Autostart und externe Umschaltung benötigen separate private Operatorprüfung. Der Test hatte bewusst keinen Docker-Socket und belegt daher keinen erneuten Sandbox-Rennbetrieb.
- Detaillierte Berichte, Datenkopien und Pakete bleiben außerhalb Git in einem owner-privaten Windows-Nachweisverzeichnis. Dieser öffentliche Bericht enthält keine Credentialwerte, Passworthashes, Datenbanken, Lernendencodes oder Backups.

## Fortsetzung

Diese Windows-Korrekturen vor dem nächsten Host-Backupwerkzeug-Lauf übernehmen. Sie ändern die Host-CLI; ein App-/Tunnel-Deployment ist dafür nicht erforderlich. Für Deployment/Migration weiterhin [RESTORE.md](../../deploy/RESTORE.md) befolgen und die aktuelle Server-/Accountrealität lesen. Die unabhängige Mac-Reserve ist keine automatische Replikation des Windows-Datenbestands.

## Sources

[1] https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-security-identifiers — Microsoft: security identifiers and OWNER RIGHTS
