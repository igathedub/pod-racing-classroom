# Einheitlich kollisionsfreie Rennen

## Regel

Testlauf, Qualifikation und Finale verwenden dieselbe kollisionsfreie Rennphysik. Pods können sich überlappen und durcheinander hindurchfahren, ohne sich abzubremsen, anzustoßen oder Kontrollpunkte gegenseitig zu verhindern. Das Finale bleibt ein gemeinsames Rennen mit bis zu fünf zugelassenen Bots; Auswahl, eingefrorene Quellcodeversionen und gültige Zielankunft als Voraussetzung für den Champion bleiben unverändert.

- Kollisionszeitberechnung, Stoßimpulse, Kollisionsmasse und Kollisionsschalter sind aus der Engine entfernt. Kein Aufrufer kann den Kontaktmodus versehentlich wieder aktivieren.
- Jeder Pod verarbeitet seine Kontrollpunkte und Rundung unabhängig. Auch Kontrollpunktzeitpunkte anderer Pods beeinflussen seine Bahn nicht durch Rundungsunterschiede.
- Neue laufende und fertige Replays tragen weiterhin das kompatible Metadatenfeld `collisions: false`.
- Neue Rennen sind sowohl bei `legacy` als auch bei `checkpoint-only` kollisionsfrei. Die Beobachtungs-/Ausgabeprotokolle werden nicht geändert.
- BOOST, Drehbegrenzung, Reibung, Rundenzahl, Kontrollpunktradius und Zeitlimits bleiben erhalten. `SHIELD` wird für vorhandene Bots weiter akzeptiert und unterdrückt wie bisher drei Züge lang die Beschleunigung, hat aber keine Kollisionswirkung.

## Historie und Anzeige

Bereits gespeicherte Replays, Ranglisten und Champions werden nicht umgeschrieben oder neu berechnet. Ein altes Finale kann daher weiterhin sichtbare Zusammenstöße und seine damalige Kontakt-Kennzeichnung haben. Die neue Regel gilt ab dem nächsten ausgeführten Rennen.

Die verzögerte Champion-Anzeige darf nicht vom alten Kollisionsflag abhängen: Schüler- und Beameransicht zeigen den Sieger erst am Ende des tatsächlich als Finale archivierten Replays. Ein Qualifikationssieg allein enthüllt ihn nicht. Die Lehrkraft darf ihn weiterhin direkt sehen.

## Regressionen und Abnahme

Neue Tests wurden vor der jeweiligen Umsetzung rot ausgeführt und anschließend grün:

- Einzelbahn gegenüber gemeinsamem Lauf bei Auffahren, Gegenverkehr, Überlappung, fünf Pods und SHIELD; einschließlich eines nachgewiesenen Gleitkomma-Rundungsgrenzfalls.
- Kein Kollisionsparameter in `advance_turn` / `run_race`; neue Fünfer-Rennen unter beiden Eingabeprotokollen melden `collisions: false`.
- Testlauf, sämtliche Archiv-Schreibvorgänge einschließlich Live-Metadaten, Qualifikation und Finale sind konsistent. Ein vorhandenes Kollisionsarchiv bleibt bytegleich.

Weitere Browser-, Gesamt- und native Docker-Prüfungen werden mit tatsächlichen Ergebnissen im PR und privaten Betreiberbericht dokumentiert. Keine Tests an echten Unterrichtsabgaben oder echten Wettbewerbszuständen durchführen.

## Backup und Primär

Den Fix eigenständig prüfen und versionieren. Auf Backup zusätzlich die noch separat freizugebende variable Abgabezeit aus PR #15 beibehalten; dafür einen ausdrücklichen Integrationsstand bauen und prüfen, statt das Timer-Feature durch Rückkehr zu main zu verlieren. Primär ist ein separates Deployment nach Freigabe, mit eigenen Daten und Zugangswerten.
