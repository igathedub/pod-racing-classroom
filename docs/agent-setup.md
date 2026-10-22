# Safe AI-assisted setup / Sichere KI-Einrichtung

Use an agent with local filesystem/terminal access only if you trust it. Docker controls powerful host facilities. These prompts authorize a **new isolated local installation**, not changes to a running classroom. Review commands before allowing them. Never paste the teacher key into the conversation.

**Release status:** v1.0.0 is the intended first stable release, not a claim that it is already published. The prompts explicitly verify availability and pin it only once available. See the [English](../README.md) / [German](../README.de.md) manual setup.

## Copyable English prompt

```text
Set up a NEW local Pod Racing Classroom installation from the public MIT project
https://github.com/igathedub/pod-racing-classroom for Codeweek 2026 Wiesbaden.
Read its public README and SECURITY.md before acting.

Discover my actual OS, Docker/Compose availability and chosen new folder first.
Do not modify, stop, reset or inspect secrets from any existing classroom.
Docker with Linux containers is required; do not install host Python, Git or Node
for the prebuilt path. If Docker installation/start needs privileges, ask me.

Check GitHub Releases for published stable v1.0.0 and its actual asset named
Pod-Racing-Classroom-v1.0.0.zip. If published, download that version, not latest
or GitHub's automatic source archive. Check any published checksum; if none is
available, state that. Inspect the package before running Start.cmd (Windows)
or sh Start.sh (macOS/Linux). Require version-pinned app and bot images, not
latest. Verify actual pull success; do not invent available assets/images.
If v1.0.0 is unavailable, explain that before proceeding. The explicit source
fallback is commit 804ac8804dff8b29d0e1ccc4364bd29d0b46fdf2, not a stable release:
use a source archive and Docker-start.cmd / sh Docker-start.sh. Ask me to approve
this fallback rather than silently replacing a release with an arbitrary branch.

Use a new dedicated folder, a UUID-suffixed unique Compose project name and a
new data volume. Persist that project name for subsequent starts. Fresh setup
must explicitly select POD_INPUT_PROTOCOL=checkpoint-only, POD_BIND=127.0.0.1
and port 8765 unless occupied; never stop another service to free it.
Do not enable LAN access, firewall rules, port forwarding, invitations, tunnels,
public hosting or change any live configuration. Ask before expanding scope.

Start and verify container health, sandbox availability, teacher/student/projector
HTTP pages, and localhost-only port binding. Do not execute bot code on the host.
Tell me how to read the independently generated teacher key in local logs; never
copy it, claim tokens, invitation codes or unredacted logs into chat/output.
Explain that the app Docker socket is host-admin-equivalent, and this setup is
not suitable for anonymous internet code execution.

Report exact folder, version/commit, Compose project name, local URLs, checks
actually run and failures/skips. Show the data-preserving stop/restart procedure.
No reset, prune, down --volumes or deletion. Do not run a competition without my
approval; if I request a demo, use only this new empty synthetic classroom.
Preserve .env, project name, volume and teacher key during future updates.
```

## Kopierbarer deutscher Prompt

```text
Richte eine NEUE lokale Pod-Racing-Classroom-Installation aus dem öffentlichen
MIT-Projekt https://github.com/igathedub/pod-racing-classroom für Codeweek 2026
Wiesbaden ein. Lies zuerst die öffentliche README und SECURITY.md.

Ermittle tatsächliches Betriebssystem, Docker/Compose und einen neuen Zielordner.
Keine bestehende Klasse verändern, stoppen oder zurücksetzen und keine privaten
Schlüssel auslesen. Docker mit Linux-Containern ist Voraussetzung. Für das fertige
Paket kein Host-Python, Git oder Node installieren. Bei benötigten Adminrechten
für Installation/Start von Docker nachfragen.

Prüfe, ob das stabile Release v1.0.0 samt tatsächlichem Asset
Pod-Racing-Classroom-v1.0.0.zip veröffentlicht ist. Nur diese Version laden,
nicht latest oder GitHubs automatisches Quellcodearchiv. Veröffentlichte Prüfsumme
prüfen; falls keine existiert, das offen sagen. Paket vor Start.cmd (Windows)
oder sh Start.sh (macOS/Linux) prüfen. Versionierte App-/Bot-Images verlangen,
keine latest-Tags; echten Download verifizieren, keine Verfügbarkeit erfinden.
Falls v1.0.0 fehlt: ausdrücklich erklären. Als Quellcode-Fallback ist Commit
804ac8804dff8b29d0e1ccc4364bd29d0b46fdf2 vorgesehen, kein stabiles Release.
Dafür nach meiner Zustimmung Quellcodearchiv und Docker-start.cmd beziehungsweise
sh Docker-start.sh verwenden, nicht stillschweigend einen beliebigen Branch.

Eigenen neuen Ordner, eindeutigen Compose-Projektnamen mit UUID-Suffix und neues
Datenvolume verwenden. Projektnamen für weitere Starts speichern. Neuinstallation
explizit mit POD_INPUT_PROTOCOL=checkpoint-only, POD_BIND=127.0.0.1 und Port 8765;
bei belegtem Port ausweichen, keinen fremden Dienst stoppen. Keine LAN-Freigabe,
Firewall, Portweiterleitung, Einladung, Tunnel, öffentliche Bereitstellung oder
Live-Konfiguration ändern. Für mehr Umfang erst meine Zustimmung einholen.

Container-Health, Sandbox, Lehrkraft-/Lernenden-/Beamer-HTTP-Seiten und reine
Localhost-Portbindung prüfen. Bot-Code niemals auf dem Host ausführen. Mir nur
zeigen, wie ich den unabhängig erzeugten Lehrkraft-Schlüssel lokal im Log lese;
ihn und andere Tokens/Codes/ungeschwärzte Logs niemals im Chat wiedergeben.
Erklären: Docker-Socket der App entspricht Host-Adminrechten; dieser Aufbau ist
nicht für anonyme öffentliche Codeausführung geeignet.

Exakten Ordner, Version/Commit, Projektnamen, lokale URLs, echte Prüfergebnisse
und ausgelassene/fehlgeschlagene Tests nennen. Datenerhaltendes Stoppen/Neustarten
erklären. Kein Reset, Prune, down --volumes oder Löschen. Wettbewerb nur nach
Zustimmung; Demo ausschließlich in dieser neuen leeren Testklasse. Bei Updates
.env, Projektname, Volume und Lehrkraft-Schlüssel erhalten.
```

## Acceptance checklist

- Local teacher, student and projector pages respond; the sandbox is available.
- Host-published port binds only to loopback; no existing installation was touched.
- New classroom has a separate project/data volume and explicit checkpoint-only protocol.
- Teacher reads their own key privately; no credential appears in the report.
- Exact version and real checks are recorded. A basic page check is not a race test or hardware-platform certification.
- macOS users run an approved isolated demo before teaching: no fresh Mac hardware acceptance is implied by the prompt.
