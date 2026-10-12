# Pod Racing Classroom

A local website for a Python coding session, alias-based submissions, fair qualification, and an animated final between the best five programs. No CodinGame account or internet service is required during the event once dependencies and the sandbox image have been installed.

This is an **independent classroom game**, not CodinGame's official referee. It preserves the beginner two-line observation/one-line action interface. The five-pod final is deliberately a classroom variant; it is not Gold-league two-pod play.

## English / Deutsch

Use the language selector in the header on any student, teacher or projector page. The selection is saved in that browser. Links such as `/teacher?lang=de`, `/?lang=de` and `/projector?lang=de` open German explicitly; `?lang=en` selects English. Switching does not reload the page or discard source drafts, aliases, private keys or replay playback position.

The visible session name is **Coding session** in English and **Programmierphase** in German. The default submission window remains two hours (7200 seconds). Instructions, controls, accessibility labels, known validation messages, rules and starter comments are localized; Python identifiers, protocol tokens, submitted code and aliases remain unchanged. Unknown technical diagnostics are preserved rather than mistranslated.

## Install on another computer (recommended: Docker Compose)

[Deutsche Anleitung / German instructions](README.de.md)

The host needs **only Docker with Compose** and the source folder: Docker Desktop in **Linux-container mode** on Windows/macOS, or Docker Engine with the Compose plugin on Linux. No host Python, uv, Node.js or npm is needed. Start Docker before proceeding. Internet is needed for the first image/dependency build; the classroom then runs locally without a cloud service.

1. Copy/extract the source folder, or clone it if Git is installed:
   ```text
   git clone https://github.com/igathedub/pod-racing-classroom.git
   cd pod-racing-classroom
   ```
   This repository is private: cloning/downloading requires an authorized GitHub account. Students do not need GitHub accounts. Do not distribute GitHub credentials, local databases or teacher keys with the source.
2. In that folder, run:
   ```text
   docker compose up --build -d
   docker compose ps
   docker compose logs classroom
   ```
   Wait for `classroom` to be **healthy**. Compose builds `sandbox/Dockerfile`, tags it `pod-classroom-bot:local`, runs a trusted completion marker, and only then starts the app. Read the generated **Teacher admin token** from the classroom logs; there is no hardcoded/default password. The token is generated independently for each fresh data volume and printed again on every launch. Keep these logs private.
3. Open `http://localhost:8765/teacher`, enter the token, and use `http://localhost:8765/projector` for projection. The safe default publishes only to this computer (`127.0.0.1`).
4. For students on a **trusted private classroom LAN**, create a file named `.env` beside `compose.yaml`:
   ```dotenv
   POD_BIND=0.0.0.0
   POD_PORT=8765
   ```
   Then run `docker compose up -d`. Give students `http://YOUR-CLASSROOM-LAN-IP:8765/`; do not use a Docker/VPN address. Allow only the private/local-subnet firewall rule described below, and test the link from another device. Never forward this port to the Internet. To return to local-only operation, set `POD_BIND=127.0.0.1` and run `docker compose up -d` again.

**Launch conveniences:** double-click `Docker-start.cmd` on Windows, or run `sh Docker-start.sh` on macOS/Linux. These run the same build/start, wait for health, and display the teacher token. Closing the launcher does not stop the detached containers. If port 8765 is occupied, set `POD_PORT=18765` in `.env`; use that port in URLs/firewall rules. `POD_BIND` accepts `127.0.0.1` or `0.0.0.0` (IPv4).

### Stop, restart, update and preserve data

```text
docker compose stop
docker compose start
docker compose logs classroom
```

`docker compose down` removes this project's containers/network **but retains classroom data**. To start again, use `docker compose up -d`. Sessions, submissions, frozen entries, replays and the teacher key live in the project-scoped named volume `classroom-data` mounted at `/data`, not in the source folder. Reusing the same folder/project name retains that volume; moving/renaming it can select a new one. Keep the same Compose project name for updates (`docker compose -p YOUR-NAME ...` if you explicitly chose one). After updating source, run `docker compose up --build -d`; stop/finish active tournaments before updating. Interrupted jobs are marked failed, not silently resumed.

**Do not run `docker compose down --volumes` on the real classroom unless you deliberately want to delete all its data and teacher key.** No launcher uses that command. Copying the source to another computer creates an independent empty classroom; it does not transfer the existing competition. For a backup, stop the app and archive `/data` using a trusted volume-backup tool/container; restore the complete volume to the same mount on the destination. Backups contain student source and private keys: treat them as confidential. The teacher UI's explicit reset clears the competition while preserving the teacher key.

### Docker permissions and rootless Linux

**The app's `/var/run/docker.sock` mount is host-admin-equivalent access.** The app service is trusted administrative software, not a sandbox for untrusted code. It runs as root to access common Docker sockets. Only the app service receives the socket; **student bot containers never receive the socket, host mounts or network access**. Do not expose this HTTP service publicly, use an unauthenticated TCP Docker daemon, or treat a read-only socket mount as a security boundary.

For rootless Linux, set the real socket path in `.env`, for example:

```dotenv
POD_DOCKER_SOCKET=/run/user/1000/docker.sock
```

Use your actual user ID/socket path, not necessarily 1000. The host Compose client must target the **same daemon** (the correct Docker context, or `DOCKER_HOST=unix:///run/user/1000/docker.sock`). Inside the app, `DOCKER_HOST` explicitly points at the mounted socket `/var/run/docker.sock`; a Windows `npipe://` host setting must not leak into the Linux app. A missing socket is an error, not an automatically created directory. Remote Docker contexts are not the default supported setup: builds, image tag and mounted socket must all refer to the same Linux daemon. The host must permit the runner's memory/CPU/PID limits; rootless resource enforcement depends on cgroup support and should be preflighted on the destination.

The digest-pinned Python, uv and Docker CLI base images include Linux AMD64/ARM64 variants, and Compose does not force an architecture. **Verified here:** an AMD64 Linux app container using Docker Desktop's real Linux daemon on Windows, including six-entry qualification, a five-bot final, secret/replay persistence after restart and container recreation. macOS, native Linux and ARM64 hardware have not been exercised here; test the demo on the target machine before the workshop. Build tools and development dependencies are not installed in the runtime image.

### Troubleshooting

- **Unhealthy / Docker unavailable:** start Docker, ensure Linux containers are selected, check `docker compose logs classroom` and `docker compose ps`, and verify the socket/daemon context match. The app checks both daemon and sandbox image and fails closed; it never executes uploads on the host.
- **Port already in use:** select another `POD_PORT` in `.env` and run `docker compose up -d`.
- **Students cannot connect:** enable `POD_BIND=0.0.0.0`, use the host's private LAN IP and selected port, check the firewall and Wi-Fi client isolation. Linux Engine may publish ports outside ordinary host-firewall rules; ask IT to verify actual exposure, not just a firewall GUI setting.
- **Cannot clone private repository:** authenticate Git with an authorized account, or ask its owner for a source archive; never put access tokens in commands/documents sent to students.
- **Teacher token lost:** `docker compose logs classroom`. On restart the same persisted key is printed again. Do not delete the volume to recover a key.

## Optional native Windows setup (Python/uv on the host)

1. Install/start **Docker Desktop** with Linux containers. Install **uv** if needed: https://docs.astral.sh/uv/getting-started/installation/
2. Double-click **Setup.cmd** once. This installs pinned application dependencies and builds the restricted Python bot image. Internet access is needed for this first setup.
3. Double-click **Start-classroom.cmd**. Keep that window open. It prints the teacher address, projector address, candidate student LAN addresses and teacher admin token.
4. Open `http://localhost:8765/teacher`, enter the admin token printed in the server window, and click **Open coding session**.
5. Give students the printed `http://YOUR-LAN-IP:8765/` address. Use your classroom Wi-Fi/Ethernet IP, not Docker or VPN adapters. Students submit an alias and paste/upload a Python file. They can replace their own submission before the deadline using the same browser's saved claim token.
6. At the end, close submissions (or allow the server deadline to close them), then **Run qualification**. Watch race progress and replays on the teacher/projector pages.
7. Once qualification finishes, click **Run final**. Open `http://localhost:8765/projector`, choose fullscreen, and project the animated race and finishing order.

If fewer than five valid entries exist, the final uses the actual number available, with at least two required. Invalid programs do not qualify.

### Network access

Windows may ask whether to allow Python on your network: allow only your **private classroom network**. School guest Wi-Fi sometimes blocks device-to-device connections; ask IT for an appropriate local network. Do not configure router port forwarding or expose this service to the Internet.

If needed, an administrator can explicitly allow TCP8765 from the local subnet on a Private network:

```powershell
New-NetFirewallRule -DisplayName 'Pod Racing Classroom' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -Profile Private -RemoteAddress LocalSubnet
```

This command is optional, requires administrator approval, and is not run automatically. Removing that rule after the workshop is recommended.

### Command-line launch

```text
uv sync --frozen --python 3.11
docker build -t pod-classroom-bot:local sandbox
uv run python launch.py --host 0.0.0.0 --port 8765
```

For use only on the teacher's computer, omit `--host 0.0.0.0` (the default is localhost). `POD_DATA_DIR` selects another database/replay directory; the default is `data/`. Keep one server process/worker, because this local version uses a single tournament worker.

## Student interface

Download the starter from the website. Each turn your program reads:

```text
x y checkpoint_x checkpoint_y distance relative_angle
opponent_x opponent_y
```

Then prints:

```text
target_x target_y thrust
```

- Coordinates are integers. The visual course is 16000 by 9000 units.
- Numeric thrust is 0..100 (out-of-range integers are clamped). `BOOST` provides one stronger acceleration per race; later BOOST commands behave like thrust 100.
- `SHIELD` prevents thrust and makes the pod heavier for its activation turn and the next two turns. The first turn may face the target freely; subsequent turns rotate by at most 18 degrees.
- In the final, the opponent line describes the **nearest other pod**. Do not assume there are only two participants.
- Keep `while True` and read both lines every turn. Keep variables outside the loop when they must survive across turns.
- Use `print(..., flush=True)` for actions. Send debugging to `sys.stderr`, not to the action channel.
- Syntax errors are rejected at submission time. Runtime errors, missing output, excessive output and turn timeouts are reported by the referee.
- Only Python's standard library is available in the isolated bot environment. Uploaded programs do not get network access, host files or your installed packages.

Use the site rules as the authoritative description of the implemented classroom engine, including shield behavior and timeout/ranking details.

## How the competition is scored

**Qualification:** each student runs the same three deterministic courses from the same starting position, with collisions disabled and a trusted reference opponent. This measures the student's racing behavior fairly rather than rewarding luck in a particular pairing. Rank completed courses first, then the tournament's recorded time/progress tiebreakers. A disqualified program cannot enter the final. All submitted source versions are frozen when qualification begins.

**Final:** up to five best valid programs race together with collisions enabled. They use the frozen source, not any later edits. The replay records every turn and the referee's finishing order. The website reports when no valid finisher exists instead of silently declaring a crashed program the champion.

## Teacher workflow

Before the children arrive:

- Start Docker Desktop and the website; verify the sandbox indicator is ready.
- Test the student link from another device on the classroom network.
- Use the **demo** in an empty session to run genuine example programs and rehearse qualification/final.
- Reset the demo using the explicit reset confirmation before starting the real session.
- Keep the teacher token private; do not project the teacher login field.
- Have students keep copies of their source code. Alias replacement ownership is stored in their browser; clearing local storage/using another browser loses the saved claim token.

During the two-hour exercise, encourage students to start with a working checkpoint-following bot, then experiment with turning, slowing down, boost timing, and remembering earlier positions. This is a beginner programming activity; no machine learning or genetic algorithm is necessary.

The clock and submissions persist across server restarts. An interrupted tournament is reported as failed rather than left looking permanently active. Do not reset the database during a running tournament.

## Safety and limitations

All uploaded source is executed **only inside restricted Docker containers**. The app fails closed if the Docker daemon/image is unavailable; there is no unsafe host-execution fallback. Containers use no network, no host mounts, non-root users, a read-only root filesystem, dropped capabilities, and resource/output limits. The teacher's admin token and student ownership tokens are not public leaderboard data.

Docker is a practical isolation boundary, not a mathematical guarantee against every kernel/runtime vulnerability. Keep Docker Desktop updated, run this on a trusted private classroom network, avoid sensitive host sharing, and use a disposable machine/VM for hostile public submissions. The HTTP site is not designed for public hosting or transmitting secrets across untrusted networks.

The initial classroom release has a 60-submission cap. Qualification runs sequentially to bound resource use; final participants have separate persistent containers. Preflight a realistic class size on the machine before the event. Race replay playback can be paused, sped up, scrubbed or replayed; it need not match the time the CPU spends evaluating programs. Projector playback hides the champion until the finish and fits the camera to include drifting pods.

Each race is two laps, with a maximum of 700 turns. Bots have 0.5 seconds to answer a normal turn, 2 seconds for their first turn, and 15 seconds for container startup. Output caps apply across the entire race: 1 MiB stdout, 64 KiB stderr, 1 KiB per command line. Resource limits are 64 MiB memory, half a CPU and 32 processes per bot. The teacher secret is printed again on restart; keep the console private.

## Development and verification

```text
uv run pytest -m "not docker"
uv run pytest -m docker
uv run ruff check arena tests scripts launch.py
uv run python scripts/smoke_tournament.py
uv run python scripts/browser_smoke.py
uv run python scripts/i18n_browser_test.py
uv run python scripts/deployment_test.py
```

The smoke test uses a disposable database, submits genuine Python programs, runs Docker qualification and the five-pod final, checks invalid-program exclusion and saves evidence under `artifacts/`. It does not seed the actual classroom database.

The browser test drives the student and teacher controls through Playwright, then checks a real five-bot Docker final, projector playback, mobile layout, JavaScript errors and persistence after a server-process restart. It uses installed Edge or Chrome when available. See `VERIFICATION.md` for the verified release results.

The Compose deployment test uses a randomly named project, an unused localhost port and a disposable named volume. It exercises the real containerized API/Docker runner, six-bot qualification, five-bot final, then verifies the generated teacher key, submissions, leaderboard and replay after both restart and container recreation. It deletes only its own containers/volume, retains the shared sandbox image and writes `artifacts/deployment-result.json`.

Architecture: FastAPI + SQLite + Python deterministic engine + Docker Python bots + vanilla HTML/JavaScript Canvas. No CDN assets, frontend build step, cloud service, or paid API.

Original application source is MIT-licensed; third-party dependencies retain their own licenses. Research references include the MIT Coders Strike Back referee, but compatibility with the official current engine is not claimed.
