# Pod Racing Classroom

**Python bots. Fair qualification. A three-track classroom final.**

Made for **Codeweek 2026 in Wiesbaden**. Students use a browser; the teacher runs Docker. English/German student, teacher and projector views include private practice and animated replays. An independent game inspired by CodinGame, not its official referee or an affiliated product; one pod per student, not Gold-league team play.

[Deutsch](README.de.md) · [Documentation](docs/README.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)

## Start v1.0.0

**Requires Docker with Compose v2**, running before launch: Docker Desktop in **Linux-container mode** on Windows/macOS, or Docker Engine with the Compose plugin on Linux. **No host Python, Git, Node.js, npm or uv needed.** First start downloads images and needs internet; subsequent classroom use is local.

1. Download [**Pod-Racing-Classroom-v1.0.0.zip**](https://github.com/igathedub/pod-racing-classroom/releases/download/v1.0.0/Pod-Racing-Classroom-v1.0.0.zip) from the [published stable release](https://github.com/igathedub/pod-racing-classroom/releases/tag/v1.0.0), check it against [SHA256SUMS](https://github.com/igathedub/pod-racing-classroom/releases/download/v1.0.0/SHA256SUMS), and extract into a new, dedicated writable folder. Use this asset, **not** GitHub's automatic “Source code” archive or historical source-only `v1.0.0-preview.1`.
2. **Windows:** double-click `Start.cmd`. **macOS:** use `Start.command`, or `sh Start.sh` in Terminal if blocked. **Linux:** `sh Start.sh`. The launchers pull pinned app/bot images; no source build.
3. Wait for healthy startup. Open **http://localhost:8765/teacher** and privately read the **Teacher admin token** from **`teacher-private.log`** in that folder. The key is generated locally and saved with owner-only permissions, not printed to the launcher console. Never share or project the file/token.
4. Student page: **http://localhost:8765/**. Projector: **http://localhost:8765/projector**. These URLs work **on this computer only**; the ZIP fixes `127.0.0.1:8765`, ignores ambient `.env`, and opens no firewall, tunnel or LAN access.

If port 8765 is occupied, do not stop an unrelated service. Resolve the conflict or choose an explicitly configured [source installation](docs/source-installation.md). For checksum commands, immutable image digests and platform limits, see [verification](VERIFICATION.md). For reviewed setup automation, use the [safe agent prompt](docs/agent-setup.md).

## Try the demo, then teach

On this **new empty demo installation**, use the teacher view to add six demo bots, run qualification, then the three-track final: **18 qualification races + 3 finals = 21 replays**. Project the replay view, not teacher credentials. Never reset a real classroom to try the demo. Preflight the complete flow on your target computer before teaching, especially on macOS/ARM64.

![Real projector view with synthetic pilots and three-track standings](docs/media/demo.png)

[Watch the replay demo (WebM)](docs/media/demo.webm) · [Capture provenance](docs/media/README.md). Real application captures with synthetic pilots, not platform certification.

1. At `/teacher`, open the coding session: **120 minutes** by default, configurable to **1–1440 whole minutes**. Setting remaining time counts from that click; invitation expiry is separate.
2. Students choose an alias and paste/upload Python. The same browser's private claim key permits updates before the deadline. Save source separately; the claim key is not the teacher key. Private practice does not enter the competition.
3. Close submissions and run qualification; source versions are frozen. Up to **100 submissions**, not 100 simultaneously running pods.
4. Run the final: the best eligible **up to five** bots, at least two required. **Final overall** is separate from the current race's positions.

Teacher deletion requires confirmation, is blocked during a race/job, and removes **all replays containing that bot**, including shared final replays. It is not a permanent participant ban.

## Rules and Python interface

Fresh release ZIP installations use **one input line per turn**, with no opponent-coordinate line:

```text
x y checkpoint_x checkpoint_y distance relative_angle
```

Output one action and flush it:

```text
target_x target_y thrust
```

Read the website's starter and rules for the **active installation**. An existing `legacy` installation sends a second opponent line; changing protocols breaks bots that still read it. The checkpoint-only Nadja starter must **not** read an enemy line.

- Python standard library only. Keep persistent state outside the loop. Use `print(..., flush=True)`; debugging goes to `sys.stderr`.
- Numeric thrust is 0–100 (out-of-range integers are clamped). `BOOST` works once per race; later uses behave as thrust 100. `SHIELD` suppresses thrust on its activation turn and the next two turns; it has no defensive effect without collisions.
- Practice, qualification and final all run without collisions. Pods cannot push or block each other.
- Qualification uses the same three deterministic courses for every bot: Wide Circuit, Five Corners and Switchback. A disqualified bot cannot enter the final.
- The final uses **Hairpin Run, Diamond Loop and Technical Loop**. The lowest sum of the **three unrounded final finish times** wins; qualification times do not count. These are fractional **simulated turns, not real seconds**. Display rounding does not affect ranking.
- A champion must finish all three final tracks without disqualification. Otherwise the result is DNF/DQ; if nobody has a valid total, there is no champion. Exact total ties use case-folded alias, then UUID.
- Teacher views can show the aggregate immediately. Student/projector views reveal it after the third current final replay finishes, once the series/job is complete. This presentation timing is not an API secrecy boundary.

More: [three-track scoring](docs/three-track-final.md) · [submission-window controls](docs/configurable-submission-time.md).

## Stop, restart and update — keep your data

- **Stop:** `Stop.cmd` / `Stop.command` / `sh Stop.sh`. **Resume:** the matching Start launcher in the **same folder**. Closing the window does not stop detached containers. Do not use plain `docker compose stop/start` for the ZIP: it omits the saved project/defaults/socket setup.
- Keep **`.classroom-project`**: it identifies the project-scoped `classroom-data` volume (`/data`), containing sessions, source, frozen entries, replays and the teacher key. A new folder/project can make existing data appear missing. Do not run two copies sharing that project file.
- Before updates, finish active jobs, stop, and privately back up the **complete data volume and installation state**. A copied ZIP folder is **not a data backup**. Review release notes/checksums; extract a newer verified ZIP **over the same folder**, retaining `.classroom-project`, volume and teacher key, then use Start. Never reset, prune volumes or use `down --volumes` to update/recover. Interrupted jobs fail rather than resume.

## Security and platform scope

Bots run only in restricted Docker containers: no network, Docker socket or host mounts; non-root, read-only filesystem, dropped capabilities and resource/output limits. Missing sandbox fails closed, with no host-execution fallback. **The trusted app's Docker socket is host-admin-equivalent access**; Docker cannot guarantee protection from kernel/runtime flaws. Public source availability is **not authorization for anonymous internet code execution**. Read [SECURITY.md](SECURITY.md); genuinely hostile code needs independently reviewed isolation, such as a dedicated disposable VM.

The release ZIP and public Linux AMD64 images have been checked; Windows Docker Desktop exercised the complete demo and restart. Native Linux AMD64/ARM64 **source-build CI** is distinct from published-image execution. No native Mac Docker acceptance or published ARM64 image execution is claimed. See [current verification](VERIFICATION.md) and [reported load measurements](docs/performance.md); 100 logical clients are not 100 smoothly rendered browsers.

## Help and advanced setup

- **Docker unavailable/unhealthy:** start Docker in Linux-container mode, retry Start and inspect errors locally.
- **Data looks empty:** check the original folder and `.classroom-project`; do not reset or create data over it.
- **Lost teacher key:** run Start and privately read `teacher-private.log`. No shared/default password; never delete the volume or share unredacted logs to recover it.
- [Source builds, trusted LAN and rootless configuration](docs/source-installation.md) are advanced, explicit alternatives, not ZIP `.env` settings. No LAN/internet deployment is performed by this guide.
- [Documentation index](docs/README.md) · [Contributing](CONTRIBUTING.md) · [GitHub Issues](https://github.com/igathedub/pod-racing-classroom/issues). Report vulnerabilities via [SECURITY.md](SECURITY.md). Original code is [MIT licensed](LICENSE); dependencies retain their licenses.
