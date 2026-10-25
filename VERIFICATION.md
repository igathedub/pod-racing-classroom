# Current verification: v1.0.0

This page separates published release evidence, recorded isolated acceptance and remaining platform gaps. It does **not** certify a live website deployment. The normal installation route is the [English](README.md) / [German](README.de.md) Docker-first quickstart.

## Published stable release

- [v1.0.0](https://github.com/igathedub/pod-racing-classroom/releases/tag/v1.0.0) was published on **2026-10-24**, from **`691ec3939c4be2d90526a9242997e88835024dd7`**. [Release workflow 40077847212](https://github.com/igathedub/pod-racing-classroom/actions/runs/40077847212) succeeded at that SHA.
- Runtime asset: [Pod-Racing-Classroom-v1.0.0.zip](https://github.com/igathedub/pod-racing-classroom/releases/download/v1.0.0/Pod-Racing-Classroom-v1.0.0.zip), **13 files**, pull-only Compose and Start/Stop launchers; no local source build. [SHA256SUMS](https://github.com/igathedub/pod-racing-classroom/releases/download/v1.0.0/SHA256SUMS) records ZIP SHA-256 **`a3309a21150e6c50b0c07605ed87b9dbedd2dfc0fe81cb91f3a7d0bfbc535c6e`**. Anonymous ZIP/checksum downloads were checked during release acceptance.
- The earlier **`v1.0.0-preview.1`** is historical and source-only, not the stable runtime installer. GitHub's automatic source archives are also not the runtime ZIP.

After downloading the ZIP and `SHA256SUMS` into the same folder, calculate the ZIP's hash and compare the full value with the published checksum. These commands require no Python/Node/Git:

```powershell
# Windows PowerShell
Get-FileHash .\Pod-Racing-Classroom-v1.0.0.zip -Algorithm SHA256
```

```sh
# macOS
shasum -a 256 Pod-Racing-Classroom-v1.0.0.zip
# Linux: checks the filename and hash recorded in SHA256SUMS
sha256sum -c SHA256SUMS
```

The ZIP pins these immutable **multi-architecture index digests**, not mutable `latest` references:

```text
ghcr.io/igathedub/pod-racing-classroom-app@sha256:1eba5ac39786c4ebdcf3243aa9a410b0623643eaab2253352861dedb3b8edd73
ghcr.io/igathedub/pod-racing-classroom-bot@sha256:bea033350d14435f20bee9260a38e0329dd16ed8ddd2bff887a6ade07c1e0e07
```

Both images were anonymously pulled and executed as **Linux AMD64** during the public release gate. AMD64/ARM64 image configuration metadata was checked for release version/revision; a manifest/config inspection is **not ARM64 execution**.

## Hosted CI at the stable source SHA

[Main CI run 40019645128](https://github.com/igathedub/pod-racing-classroom/actions/runs/40019645128) succeeded on **2026-10-23** at `691ec3939c4be2d90526a9242997e88835024dd7`:

| Job | Evidence scope |
|---|---|
| Unit and Chromium: Ubuntu, Windows, macOS | Source tests, browser/UI behavior, distribution checks; not a native Docker classroom acceptance on each desktop OS |
| Native Linux Docker: AMD64 and ARM64 | Images **built from source** on native runners, distribution and real bot-isolation tests; not execution of the subsequently published ARM64 registry image |

The [isolated Windows PR run 40017512575](https://github.com/igathedub/pod-racing-classroom/actions/runs/40017512575) also passed before PR #19 merged. Earlier Windows CI failures are historical diagnostics, **not a current release blocker**; use the SHA-linked successful run above rather than treating earlier red runs as today's status. CI does not authorize deployment or prove target-school network access.

## Recorded isolated release acceptance

The [published release acceptance summary](https://github.com/igathedub/pod-racing-classroom/releases/tag/v1.0.0) records the following **real Docker** checks, using synthetic data and isolated test projects. They are not new runs performed merely by editing this documentation:

- Windows `Start.cmd` / `Stop.cmd`: six demo bots, **18 qualification races and three final races**, **21 replay archives**. Aggregate scores and the overall champion were reconstructed from actual race results. Restart preserved classroom data, the teacher key and access.
- Private practice left global competition state, database and archives unchanged; unauthorized ownership claims were rejected.
- Rendered student, teacher and projector views in **English and German** were exercised. Associated live sandbox children were checked for the restricted execution boundary, not inferred merely from Compose text. Synthetic resources were cleaned up.

These checks concern the collision-free, three-track release. [Three-track contract](docs/three-track-final.md), [collision-free rules](docs/collision-free-racing.md) and [media provenance](docs/media/README.md) describe their separate fixture/capture scopes. Earlier captures at `804ac8804dff8b29d0e1ccc4364bd29d0b46fdf2` are not a claim that the ZIP itself was captured.

## Limits and target-machine preflight

- **Not verified:** native Mac Docker execution, execution of the published ARM64 images, a fresh full classroom deployment on every supported OS, or school Wi-Fi/firewall access from another device. macOS source/browser CI and native ARM source CI do not fill those gaps.
- Run the six-bot demo in a **new empty installation** on the target hardware before teaching. Localhost URLs work only on the host; trusted-LAN exposure requires explicit source configuration and a second-device check.
- [Reported 100-client workload measurements](docs/performance.md) are not smooth 100-browser playback, fixed lesson duration or anonymous public-hosting capacity.
- No current `codeweek-wi.de` production revision is established by this page. A release, merge or successful CI is **not** a live deployment. Existing operators must independently verify their approved target, data, access and rollback using [rollout](deploy/ROLLOUT.md) and [restore](deploy/RESTORE.md) guidance.
- No test or documentation change relaxes [SECURITY.md](SECURITY.md): untrusted bots run only in Docker; the trusted app's Docker socket is host-admin-equivalent access. Public source is not permission for anonymous internet code execution.

## Historical results

**Historical verification only:** [original release and bilingual/portable results](docs/history/original-verification.md) retain their original context. Their collision-enabled finals are **not evidence for the collision-free release**. Old suite counts, original single-final benchmarks, native-host statements and formerly private-repository checks must not be relabeled as v1.0.0 proof. Existing competition archives remain unchanged.
