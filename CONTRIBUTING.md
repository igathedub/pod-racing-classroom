# Contributing

Thanks for helping make Python racing lessons easier to run. This public MIT application was made for **Codeweek 2026 in Wiesbaden**. Read the [safe automation guidance](docs/agent-setup.md) and [SECURITY.md](SECURITY.md) before reporting vulnerabilities.

## Issues and changes

- Search existing issues first. Use a bug report for reproducible non-security failures or a feature request for a classroom need. Include the exact commit/release, OS/architecture, Docker version and installation route.
- Never attach `.env`, teacher/claim/invitation tokens, private deployment handoffs, raw logs, classroom databases, student submissions or backups. Share a minimal synthetic reproduction and redacted diagnostics.
- Discuss larger protocol, scoring, storage or deployment changes before implementing them. Keep pull requests focused; describe behavior changes and compatibility/data risks.
- Preserve English/German documentation and UI behavior together. Independent CodinGame inspiration is not official compatibility or affiliation. Keep the MIT license and upstream notices.

## Development checks

For trusted development tooling, install Python 3.11+ and uv. From your development checkout:

```sh
uv sync --frozen --python 3.11
uv run ruff check .
uv run pytest
```

Some tests require optional Docker/browser setup and opt-in flags; inspect the relevant test/script instructions and report actual results and skips. For browser coverage, the development dependency is Playwright; install its Chromium browser with `uv run playwright install chromium` if needed. Do not claim browser/Docker coverage from mocked tests.

Student code must **never run on host Python**. Only trusted test tooling runs on the host. Docker-dependent tests need a running Linux daemon and the correct sandbox image; missing Docker is not permission to bypass isolation.

The optional real-deployment smoke tool is `uv run python scripts/deployment_test.py`. Inspect it before running: it builds and uses Docker resources. Run it only when Docker testing is authorized. It is intended to use a synthetic isolated classroom, not a live installation.

## Required safety for tests

- Use UUID-scoped temporary projects, separate synthetic volumes and localhost-only free ports. Keep ownership markers and clean up only resources created by that test.
- No production keys/data, live resets, broad prune commands or `down --volumes` against an existing installation. Never use an existing classroom as an acceptance fixture.
- Preserve sandbox fail-closed behavior, one-worker assumptions, collision-free phases, final scoring precision and protocol compatibility.
- Check restart/update data preservation where relevant. Stop active work and back up privately before approved deployment changes; a merge does not authorize a live rollout.

## Pull request checklist

- Explain the problem and smallest intended change; link a non-sensitive issue if applicable.
- Add regression tests and list exact commands/results, skips and OS/architecture.
- Update both quickstarts for user-facing behavior; check relative links.
- Separate real native hardware, CI, build, shell/unit and mock evidence.
- Do not claim a release asset/image exists until published and checked. No fabricated screenshots or benchmark results.
- Keep secrets and generated classroom artifacts out of the diff.

## Deutsch

Fehler bitte mit Version/Commit, Betriebssystem, Docker-Version und kleinem künstlichem Beispiel melden. Größere Änderungen vorab besprechen. Keine Schlüssel, echten Schülerdaten, Datenbanken, privaten Betriebsanweisungen oder ungeschwärzten Logs veröffentlichen. Englische/deutsche Doku gemeinsam pflegen. Tests nur in separaten UUID-Testinstallationen; Bot-Code ausschließlich in Docker. Echte Ergebnisse und ausgelassene Tests nennen, keine Hardware-/Release-Prüfung erfinden. Sicherheitslücken ausschließlich gemäß [SECURITY.md](SECURITY.md) melden.
