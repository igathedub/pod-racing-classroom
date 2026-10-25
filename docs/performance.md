# Performance evidence / Leistungsnachweise

These are reported synthetic workload measurements, not a new v1.0.0 benchmark or a hosting guarantee. See [current verification](../VERIFICATION.md) for release/platform scope and [moderation/load notes](teacher-moderation-and-load.md) for provenance.

## English

A reported full-workflow benchmark on a **16-logical-CPU Windows desktop** used 100 identical Nadja sources and **100 logical HTTP clients**, not 100 rendered browsers:

| Measurement | Observed result |
|---|---|
| 100 submissions | 0.645 s total; p95 571 ms |
| 300 qualification races | 858.436 s |
| Three final races | 36.192 s |
| Archives | 303; no DQ/DNF |
| Poll requests | 99,873; all HTTP 200, no timeouts |
| Final state response latency | p95 3.327 s; max 4.481 s |

Polling still missed **511 state / 1,405 replay ticks** during the final and **2,100 qualification replay ticks**. Successful HTTP responses are **not** evidence of smooth 100-browser playback, fixed classroom duration or public-hosting capacity. Different bots and hardware change runtime. Older single-final measurements in historical notes are not the current three-track workload.

## Deutsch

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
