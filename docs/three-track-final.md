# Three-track aggregate final / Drei-Strecken-Finale

## Competition rules

- Qualification remains on **Wide Circuit / Breiter Rundkurs**, **Five Corners / Fünf Kurven**, and **Switchback / Zickzackstrecke**. The qualification ranking selects up to five eligible frozen submissions; at least two are needed for a final.
- Final races use three **other** tracks: **Hairpin Run / Haarnadelkurs**, **Diamond Loop / Diamantrunde**, and **Technical Loop / Technikrunde**, in that order. Practice, qualification and all three final races are collision-free. Pods cannot push or block each other.
- Add the three final `finish_time` values. **Qualification times are excluded.** The lowest valid total wins. A single race winner, including the last race winner, is not necessarily the overall champion.
- Each time is a fractional number of **simulated turns / Spielzüge**, not wall-clock seconds, sandbox runtime, or replay presentation time. The UI shows three decimal places (decimal comma in German); it neither re-sorts rounded values nor recomputes totals.
- A total requires **all three valid finishes and no disqualification**. Otherwise the total is null: show DNF or DQ, never a winning penalty total. If nobody has a valid total, there is **no champion / kein Gesamtsieger**.
- Exact total ties use case-folded alias then UUID. The server's row order and `rank` are authoritative, even if rounded totals look identical.
- This format is **not retroactive**: old single-final competitions keep their original interpretation. Historical contact replays keep their original contact labels. No source or archived replay is rewritten by localization or playback.

## Public state and replay contract

New format marker: `final_format: "three-track-total-time-v1"` (null for legacy).

| State field | Meaning |
| --- | --- |
| `final_tracks` | List of three final track dictionaries, or empty before selection |
| `final_replay_ids` | Current series only, replay UUIDs in order 1..3; grows during work, not an archive search |
| `final_leaderboard` | Server-ordered overall rows |
| `champion` | Overall winner `{id, alias}` or null; not the last replay's winner |

Each overall row contains `id`, `alias`, `rank`, `completed_tracks`, `disqualified`, `race_times: [float|null, float|null, float|null]` and `total_time: float|null`. During work an unrun track is pending (`—`); a completed nonfinish is DNF. A disqualified row is clearly marked DQ. A final total exists only for three valid finishes.

Each final JSON includes `series_index: 1|2|3` and `series_total: 3`. Its own `winner_id` remains the individual race winner. Metadata titles are exactly `Final {i}/3 · {track[name]} · {n} pods`, localized in German to `Finale {i}/3 · {translated track name} · {n} Pods`.

Rules additionally expose `final_tracks: 3` (**number**, unlike the state list), `time_unit: "simulated_turns"` and localized `final_scoring`. New optional keys are not required when localizing historical rule/state fixtures. Translation returns request-local copies; identifiers, aliases, source, numeric times and protocol tokens are not translated.

### Worker messages

| English | German |
| --- | --- |
| `Racing {n} finalists over three different tracks.` | `{n} Finalisten fahren auf drei anderen Strecken.` |
| `Final {i} of 3 complete.` | `Finalrennen {i} von 3 abgeschlossen.` |
| `Three-track final complete.` | `Das Drei-Strecken-Finale ist abgeschlossen.` |
| `Three-track final complete; no bot finished all three tracks, so no champion was crowned.` | `Das Drei-Strecken-Finale ist abgeschlossen. Kein Bot hat alle drei Strecken beendet, deshalb gibt es keinen Gesamtsieger.` |

## UI and reveal boundaries

The three tabs are **Qualification / Qualifikation**, **Race positions / Rennplatzierungen** and **Final overall / Finale gesamt**. Final overall has Final 1/2/3/Total columns and a simulated-turn unit hint. The current replay table never silently becomes the overall table. Left/right arrow keys wrap across all three tabs; Home/End select the first/last. All six final columns remain available through local horizontal scrolling on narrow/projector layouts.

Teacher can inspect aggregate standings and the champion anytime. Student/projector aggregate table and champion require **all** of:

1. All three distinct **current** `final_replay_ids` exist as final metadata.
2. The selected and loaded replay IDs equal the last current ID (not merely a final with the same winning pilot).
3. The loaded replay has `series_index: 3`, `series_total: 3`, finished status and recorded frames.
4. Playback has reached that replay's end.
5. Both tournament job and session are finished.

First/second races, qualification, an old final (even from a failed previous attempt), missing IDs, running/failed jobs or seeking back before the finish hide the aggregate again. At the third finish, the overlay identifies the **overall champion**, with the individual race winner labeled separately. If there is no valid total it explicitly reports no overall champion. Archive selectors in student/projector views do not include winner names.

Legacy data with no final-format/current-series list preserves the original single-final reveal: matching final metadata, matching winner and finished playback end. The overall tab does not fabricate a three-track table for it. Presentation hiding is not API confidentiality: authorized API consumers can already read published state.

Submission-duration controls (whole minutes, 1–1440), invitation expiry, stored drafts, claims and source handling are independent of final scoring.

## Verification scope

`tests/test_three_track_final_ui.py` uses **real headless Chromium** through the existing `moderation_browser` fixture. Its FastAPI app, SQLite Store and replay archives are disposable synthetic fixtures. It checks both languages and student/projector/teacher views, fractional totals, differing overall/last-race winners, first/second/stale replay hiding, failed/incomplete work, no champion, keyboard/mobile behavior, and unchanged submitted-source/archive bytes. `tests/test_three_track_locale.py` checks request-local translations, optional historical fields and exact message/track/rule copy without requiring a worker or bot execution. Existing collision-free and submission-time browser suites cover legacy contact/single-final behavior and timer controls.

Example targeted development command:

```text
python -m pytest tests/test_three_track_final_ui.py tests/test_three_track_locale.py tests/test_collision_free_ui.py tests/test_submission_time_ui.py tests/test_api_locale.py -q
```

These tests do **not** execute student source, access a live classroom, demonstrate native Docker execution, or authorize deployment. Prior native/platform verification reports refer to the release they originally tested, not automatically to this new format. Preflight native runners and deployment separately under the approved isolated procedure; do not reset or migrate an active classroom to test this feature.
