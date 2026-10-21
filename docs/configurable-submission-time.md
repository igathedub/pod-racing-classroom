# Variable Abgabezeit für die Lehrkraft

In der Lehrkraftansicht unter **Programmierphase** ist **Abgabezeit (Minuten)** frei einstellbar: **1–1440 ganze Minuten**, bisheriger Standard 120 Minuten. Beim Laden wird die gespeicherte Sitzungsdauer übernommen; Polling und Sprachwechsel überschreiben eine eigene Eingabe nicht.

- Vor Start: Dauer wählen und **Programmierphase starten**.
- Bei offener Abgabe: gewünschte neue Restzeit eintragen und **Restzeit setzen**. Die ausgewählte Zeit zählt **ab dem Klick**, nicht ab dem ursprünglichen Start. Das kann die Frist verlängern oder verkürzen.
- **Jetzt schließen** beendet die Abgabe wie bisher sofort.
- Nur mit Teacher-Schlüssel und ohne laufenden Wettbewerb. Eingefrorene Qualifikation/Finale werden nicht wieder geöffnet oder zurückgesetzt. Ein bereits abgeschlossener Klassenwettbewerb bleibt unverändert gesperrt.
- Ungültige/leere/gebrochene Werte senden keinen Startauftrag. Die vorhandene API bleibt bei strikter Ganzzahlvalidierung für `duration_seconds`, 1–86400 Sekunden, mit bestehendem Teacher-/Origin-Schutz. Minuten werden im Browser in Sekunden umgerechnet.
- Diese Einstellung betrifft die **Abgabezeit**, nicht die Gültigkeit einer optionalen Klasseneinladung. Sie schaltet keine Website-/Klassensperre ein oder aus und ändert keine Teacher-/Claim-Keys.

Die Änderung verwendet die vorhandene persistierte Sitzungs-/Deadline-Logik; keine neue Datenbankstruktur und keine Migration bestehender Abgaben/Replays. Das Deployment startet keine neue Sitzung und löst keinen Klassenreset aus.

Chromium-Prüfungen mit echten Test-API-Aufrufen decken Root und `/backup`, eigene Dauer, Änderung einer laufenden Restzeit, gespeicherte Voreinstellung, Sprachwechsel, Minimal-/Maximalwert, ungültige Eingaben sowie eingefrorenen Wettbewerb ab. Alle Mutationen in diesen Prüfungen verwenden eigene temporäre Testdaten, nicht den echten Klassenraum.
