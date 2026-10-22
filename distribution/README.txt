Install Docker Desktop (Windows/macOS, Linux containers), or Docker Engine + Compose v2 (Linux).
Unzip into a writable private folder. Windows: double-click Start.cmd. macOS: Start.command (if Gatekeeper blocks it, use sh Start.sh in Terminal). Linux: sh Start.sh.
No Git, Python or Node is needed. First start downloads images and needs Internet.
Only localhost:8765 is exposed; no firewall, router, tunnel or public access is configured.
Teacher: http://localhost:8765/teacher  Projector: http://localhost:8765/projector
The teacher key is stored locally in teacher-private.log. Do not share it or Docker logs.
Stop.cmd / Stop.command / sh Stop.sh stops containers, preserving classroom data.
Start again in this same folder to resume. Never delete .classroom-project: it identifies your data.
To update: stop, back up your data, extract a newer verified release OVER THIS SAME FOLDER, start.
Do not run two copies sharing the same project file. Separate folders get separate projects/data.
No automatic data deletion or downgrade. Keep old release ZIPs for recovery.
The trusted application controls Docker. Student bots get no daemon socket and run in isolated Docker containers.
Default protocol is checkpoint-only. This is a local classroom install, not a hardened public Internet service.
Source and MIT license: https://github.com/igathedub/pod-racing-classroom
