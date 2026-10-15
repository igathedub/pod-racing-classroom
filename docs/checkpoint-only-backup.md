# Backup-Test: eine Eingabezeile pro Spielzug

## Rollout nach Backup-Freigabe

Der Einzeilenmodus wurde zunächst ausschließlich auf der Mac-Reserve getestet und anschließend vom Betreiber für den Primär-Rollout freigegeben. Diese Freigabe und ein Git-Merge aktualisieren den Windows-Container **nicht automatisch**. Ablauf und Windows-Übergabe stehen in [`deploy/ROLLOUT.md`](../deploy/ROLLOUT.md).

Ohne explizite Einstellung bleibt das bisherige zweizeilige Protokoll (`legacy`) aktiv. Für beide Rollen muss in der jeweiligen bestehenden privaten Deployment-Konfiguration `POD_INPUT_PROTOCOL=checkpoint-only` gesetzt und der Appcontainer kontrolliert neu erstellt werden. Die Basis-Compose-Datei reicht den Wert weiter; spätere lokale Overrides dürfen ihn nicht unbeabsichtigt überschreiben.

Pro Spielzug wird im neuen Modus nur diese Zeile gesendet:

```text
x y checkpoint_x checkpoint_y distance relative_angle
```

Keine zusätzliche Zeile mit Gegnerkoordinaten. Antwort bleibt `target_x target_y thrust`. Physik, BOOST/SHIELD-Regeln, Sandbox- und Ressourcenlimits bleiben unverändert. Ein neuer Replay enthält die Protokollkennung. Alte Replays bleiben unverändert lesbar.

**Breaking Change:** Bestehende Programme, die anschließend ein zweites `input()` bzw. `readline()` für `opponent_x opponent_y` ausführen, funktionieren im neuen Modus nicht. Gespeicherte Abgaben werden nicht automatisch verändert. Vor einer neuen Qualifikation müssen solche Bots angepasst werden. Die neuen gebündelten Einzeilen-Demos sind separat von den Legacy-Demos abgelegt; der Demo-Button verändert weiterhin nur einen ausdrücklich leeren, wartenden Klassenraum.

## Aktualisierte Nadja-Vorlage

- Quelle: https://github.com/igathedub/mad-pod-racing-python-solutions/blob/099e9da44ca88f707ff68fba6bd643c95c017880/solutions/05_Nadja.py
- Upstream-SHA-256: `794f8150291105e13b1266ddbffdf8a478599b7de4d34041c62cf18aeea9397d`
- Testdatei: `examples/starters/05_Nadja_checkpoint.py`
- Lokaler SHA-256: `b06a10acd7d40ca9bcfc32fa2ba78033e1e25d3fe7c4d4e66d4cb18743fec1f6`

**Einzige Korrektur gegenüber dieser Quelle:** Die alleinstehende Zeile `co` (Quellzeile 36) wurde entfernt. Sie unterbricht den Schleifenblock und verursacht sonst einen `IndentationError`. Alle übrigen Bytes einschließlich Parameter, Kommentare und Optimierungen sind unverändert übernommen.

Hinweis für die Auswertung: Die neue Quelle wendet `abs(int(i))` auf **alle sechs Eingabewerte** an, nicht nur auf den Winkel. Dadurch gehen auch negative Koordinatenvorzeichen im Bot verloren. Das ist für diesen Vergleich bewusst nicht stillschweigend geändert. Die Engine selbst liefert weiterhin korrekte vorzeichenbehaftete Werte.

Der Editor und Startcode-Download wählen die neue Datei nur im `checkpoint-only`-Modus. Legacy verwendet weiterhin die zuvor geprüfte Originaldatei. Die Kurzbeschreibung und `/api/rules` nennen dasselbe aktive Protokoll.

## Bisher tatsächlich geprüfte Ergebnisse

- Vollständige Python-Suite: 324 bestanden, 46 opt-in Tests übersprungen; eine bestehende Starlette/httpx-Warnung. Ruff für den geänderten Anwendungscode und neue Tests grün.
- 14 zusätzliche echte Docker-Protokolltests bestanden: Nadja alt/neu auf drei gleichen Kursen, sieben Einzeilen-Beispielbots und die erwartete Inkompatibilität eines alten Zwei-Zeilen-Bots.
- Nadja beendet beide Protokollvarianten ohne Disqualifikation: Wide Circuit 175, Five Corners 198, Switchback 237 Spielzüge. In diesem Vergleich keine Verbesserung der Rennzugzahl.
- Vollständiger isolierter API-Wettbewerb mit dem gebauten Appimage: sieben Bots einschließlich neuer Nadja, 21 Qualifikationsrennen, fünf Finalisten, 22 Replays, gültiger Gewinner; alle Archive tragen `checkpoint-only`. Eigenes synthetisches Volume/Container, kein Reset des laufenden Backups.

## Abnahme und Rollback

- Engine-/API-/Chromium-Tests müssen Legacy und Einzeilenmodus getrennt prüfen; ungültige Protokolle vor Datenerzeugung/Runnerstart ablehnen.
- Aktualisierte Nadja und Legacy-Nadja auf identischen Kursen in der echten Docker-Sandbox vergleichen. Keine Bot-Ausführung auf dem Host.
- Bestehende Klassen-/Replay-/Teacher-Daten privat sichern und beim Backup-Deployment vollständig vergleichen; keinen Klassenreset und keine Live-Qualifikation als Test auslösen.
- Rollback verwendet das bisherige Backup-Appimage und entfernt ausschließlich `POD_INPUT_PROTOCOL=checkpoint-only` aus dem lokalen Rollen-Override. Gleiches Datenvolume, gleiche Zugangseinstellungen und gleicher Teacher-Token; keine Rücksicherung über neuere Unterrichtsdaten.
