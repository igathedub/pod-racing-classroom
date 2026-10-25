# Historical verification: original and bilingual releases

> **Historical verification only:** the original release and bilingual/portable runs below predate collision-free racing. In particular, their collision-enabled finals are not evidence for the collision-free release. These recorded results are retained as history, not rerun or relabeled as new proof. Existing competition archives must not be changed.

For current release evidence and limitations, see [VERIFICATION.md](../../VERIFICATION.md).

## Collision-free UI and rules checks

`tests/test_collision_free_ui.py` and `tests/test_collision_free_rules.py` use synthetic data in disposable databases. Chromium checks final-kind/ID-based champion reveal only at playback end (including old contact finals), no reveal from qualification wins, unchanged archive bytes and submission records, and EN/DE instructions in both input protocols. The API rules checks preserve protocol/BOOST/SHIELD compatibility. These are not Docker race or deployment acceptance results; engine/tournament verification is separate.

## Original release verification

### Automated suite

Executed the complete project test suite against the running Docker Desktop and built sandbox image:

```text
116 passed, 1 warning in 26.42s
```

The sole warning is upstream Starlette/httpx TestClient deprecation. Ruff returned `All checks passed!`; `node --check web/app.js` exited successfully.

Coverage includes deterministic physics, checkpoint crossings/collisions, BOOST/SHIELD, bot startup/turn deadlines, output floods, real container restrictions and cleanup, submission syntax/size/ownership, teacher authorization, deadline expiry, immutable snapshots, job/reset locking, restart recovery, top-five selection and public secret/source exclusion. Public sandbox status is cached briefly to avoid one Docker probe per student poll; job preflight bypasses that cache.

## Real API acceptance test

`scripts/smoke_tournament.py` used a disposable database and genuinely executed six valid Python input-loop submissions plus one deliberately crashing submission inside Docker. All 21 qualification races ran; the crashing program was excluded from the five finalists. The five-pod collision-enabled final completed with 216 replay frames and an actual finishing winner. Syntax validation, alias ownership, late-submission rejection and public secret exclusion were checked. No fabricated race data was substituted.

## Real browser acceptance test

`scripts/browser_smoke.py` used installed Edge via Playwright and a disposable database. Latest successful run:

```json
{
  "passed": true,
  "elapsed_seconds": 23.3,
  "students": 6,
  "finalists": 5,
  "champion": "Browser Pilot 5",
  "final_frames": 224,
  "page_errors": [],
  "console_errors": [],
  "restart_persistence": true
}
```

This exercised real website submission, syntax-error display, replacement after reload, teacher session start, UI-triggered qualification/final, animated projector replay, winner overlay and 390px layouts without horizontal overflow. It verified that the winner is not announced in the replay selector/footer before playback finishes. The server was then stopped and restarted; champion, leaderboard and exact replay remained intact.

Screenshots were inspected directly. The revised camera includes all five drifting pods and readable labels. Additional agent browser checks covered file upload, code inspection, seed/reset/close, fullscreen, keyboard controls, 320/768px layouts and alias XSS protection.

These short demo runs are not a throughput guarantee for a full class or expensive student algorithms. Preflight the expected class size on the actual classroom network.

## Running classroom

At initial startup the application was read back on localhost and the host's LAN address, port 8765. Student, teacher and projector routes returned HTTP200. The classroom was deliberately empty and waiting, with a two-hour default, no test submissions/results, an idle worker and a ready restricted Docker sandbox. No `pod-bot-*` containers remained after acceptance runs.

Cross-device access through school Wi-Fi and Windows Firewall still needs a check from a student's device. No firewall or router rules were changed automatically.

## Bilingual and portable update

- Complete suite: **129 passed, 1 upstream deprecation warning in 26.42s**. Ruff and both JavaScript syntax checks passed. Compose configuration validation passed.
- English/German Edge-browser acceptance passed on an isolated HTTP server. Tested saved language, `?lang=de/en` links, translated syntax errors, controls, instructions, starter comments and server rules. Code/aliases, private keys and replay selection/pause/position/speed remained unchanged. The reference-engine playback tests used predefined trusted policies, not host execution of submitted code. Desktop and 320/390px screenshots were inspected, with no page errors or horizontal overflow.
- The full real-Docker website submission/qualification/final browser test passed again: six entries, five finalists, 224 final frames, no page/console errors and persistent results after restart.
- A fresh authenticated checkout from the private GitHub repository had no host virtualenv, local database or copied keys. Its Docker Compose installation built successfully and ran six-entry qualification and a simultaneous five-pod final, with 216 final frames. Runtime had no uv, Node/npm, pytest, Playwright or Ruff installed. Teacher key, submissions, winner and exact replay survived restart and forced container recreation. Both launch helpers worked. The isolated test completed in 54.31 seconds and removed only its own containers/volume.
- Exact inspected student containers had no network, host/socket mounts or root privileges; read-only filesystem, dropped capabilities and 64 MiB/half-CPU/32-process limits were enforced. Starting the app without its trusted Docker socket failed closed.
- The private repository's visibility and main commit were read back through GitHub. The staged-source audit verified that classroom databases, live teacher key and all current ownership tokens were excluded. Source archives also exclude private/generated data.
- The existing native classroom was updated only after its tournament was idle. Cryptographic before/after checks verified all four existing submissions, the teacher key, stored session/deadline, configuration and every saved replay were preserved. German API and the language switch were read back after reload.

The visible name is now **Coding session / Programmierphase**, with the original 7200-second default retained. A new computer creates its own empty database and teacher key; cloning does not copy the current competition. Docker Compose defaults to localhost, with explicit trusted-LAN configuration documented in English and German.

Portability was exercised as a Linux AMD64 app container on Windows Docker Desktop, not on a second physical computer. Registry images are multi-architecture; macOS, native Linux, ARM64 and rootless hardware were not directly tested. Preflight the demo on the target computer and verify access from a student device.
