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
available, state that. Inspect the package before running Start.cmd (Windows),
Start.command or sh Start.sh (macOS), or sh Start.sh (Linux). Require immutable
app and bot @sha256 digests resolved from published v1.0.0 multiarch image tags,
not :1.0.0 or latest. Verify pull success; do not invent available assets/images.
If v1.0.0 is unavailable, explain that before proceeding. The explicit source
fallback is commit 804ac8804dff8b29d0e1ccc4364bd29d0b46fdf2, not a stable release:
use a source archive and Docker-start.cmd / sh Docker-start.sh. Ask me to approve
this fallback rather than silently replacing a release with an arbitrary branch.

Use a new dedicated folder and new data volume. For the ZIP, let Start generate
and save the unique project name in .classroom-project; retain it. The ZIP ignores
ambient .env and fixes checkpoint-only and 127.0.0.1:8765 in compose.yaml.
If port 8765 is occupied, report the conflict and ask; do not silently edit the ZIP.
For an approved SOURCE installation only, save a UUID-suffixed unique project
name, a unique local POD_BOT_IMAGE tag, POD_INPUT_PROTOCOL=checkpoint-only and
POD_BIND=127.0.0.1 in .env; port 8765 may use POD_PORT if occupied. Check that the
chosen revision's root compose.yaml supports POD_BOT_IMAGE for both services;
if not, stop and request an approved revision rather than sharing a mutable tag.
Never stop another service to free a port.
Do not enable LAN access, firewall rules, port forwarding, invitations, tunnels,
public hosting or change any live configuration. Ask before expanding scope.

Start and verify container health, sandbox availability, teacher/student/projector
HTTP pages, and localhost-only port binding. Do not execute bot code on the host.
Tell me how to read the independently generated teacher key privately: ZIP Start
saves owner-private teacher-private.log instead of printing the token to console;
source installations use local app logs. Do not read the key yourself. Never
copy it, claim tokens, invitation codes or unredacted logs into chat/output.
Explain that the app Docker socket is host-admin-equivalent, and this setup is
not suitable for anonymous internet code execution.

Report exact folder, version/commit, Compose project name, local URLs, checks
actually run and failures/skips. Show the data-preserving stop/restart procedure.
No reset, prune, down --volumes or deletion. Do not run a competition without my
approval; if I request a demo, use only this new empty synthetic classroom.
ZIP stop/restart must use Stop.cmd / Stop.command / sh Stop.sh and the matching
Start launcher in the same folder, not plain docker compose commands that omit
the saved project. Source-only Compose commands retain the same .env/project.
Before updates, stop and privately back up the full data volume and installation
state. Extract a newer verified ZIP OVER THE SAME FOLDER, retaining
.classroom-project, volume and teacher key, then use Start. Never copy into a new
folder for an update. For source updates retain .env, project/image names and data.
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
prüfen; falls keine existiert, das offen sagen. Paket vor Start.cmd (Windows),
Start.command oder sh Start.sh (macOS) beziehungsweise sh Start.sh (Linux) prüfen.
Unveränderliche App-/Bot-@sha256-Digests aus veröffentlichten v1.0.0-Multiarch-Tags
verlangen, nicht :1.0.0 oder latest. Echten Download prüfen, nichts erfinden.
Falls v1.0.0 fehlt: ausdrücklich erklären. Als Quellcode-Fallback ist Commit
804ac8804dff8b29d0e1ccc4364bd29d0b46fdf2 vorgesehen, kein stabiles Release.
Dafür nach meiner Zustimmung Quellcodearchiv und Docker-start.cmd beziehungsweise
sh Docker-start.sh verwenden, nicht stillschweigend einen beliebigen Branch.

Eigenen neuen Ordner und neues Datenvolume verwenden. Beim ZIP erzeugt Start den
eindeutigen Projektnamen in .classroom-project; behalten. ZIP ignoriert vorhandene
.env und legt checkpoint-only sowie 127.0.0.1:8765 in compose.yaml fest. Bei
belegtem Port Konflikt melden und fragen, das ZIP nicht stillschweigend ändern.
Nur bei genehmigter QUELLCODEinstallation einen UUID-Projektnamen, eindeutigen
lokalen POD_BOT_IMAGE-Tag, POD_INPUT_PROTOCOL=checkpoint-only und
POD_BIND=127.0.0.1 in .env speichern; POD_PORT darf bei Bedarf abweichen.
Prüfen, ob die Root-compose.yaml des gewählten Commits POD_BOT_IMAGE bei beiden
Diensten unterstützt; sonst anhalten und genehmigten Stand anfragen, keinen
veränderlichen Image-Tag teilen. Keinen fremden Dienst stoppen. Keine LAN-Freigabe,
Firewall, Portweiterleitung, Einladung, Tunnel, öffentliche Bereitstellung oder
Live-Konfiguration ändern. Für mehr Umfang erst meine Zustimmung einholen.

Container-Health, Sandbox, Lehrkraft-/Lernenden-/Beamer-HTTP-Seiten und reine
Localhost-Portbindung prüfen. Bot-Code niemals auf dem Host ausführen. Mir nur
zeigen, wie ich den unabhängig erzeugten Lehrkraft-Schlüssel privat lese: ZIP-Start
speichert teacher-private.log mit Eigentümerrechten statt Konsolenausgabe;
Quellcode nutzt lokale App-Logs. Schlüssel nicht selbst auslesen. Ihn und andere
Tokens/Codes/ungeschwärzte Logs niemals im Chat wiedergeben.
Erklären: Docker-Socket der App entspricht Host-Adminrechten; dieser Aufbau ist
nicht für anonyme öffentliche Codeausführung geeignet.

Exakten Ordner, Version/Commit, Projektnamen, lokale URLs, echte Prüfergebnisse
und ausgelassene/fehlgeschlagene Tests nennen. Datenerhaltendes Stoppen/Neustarten
erklären. Kein Reset, Prune, down --volumes oder Löschen. Wettbewerb nur nach
Zustimmung; Demo ausschließlich in dieser neuen leeren Testklasse.
ZIP nur mit Stop.cmd / Stop.command / sh Stop.sh und passendem Start-Helfer im
selben Ordner stoppen/neustarten, nicht mit einfachen docker compose-Befehlen
ohne gespeichertes Projekt. Compose-Befehle nur für Quellcode mit gleicher .env.
Vor Updates stoppen und vollständiges Datenvolume samt Installationszustand
privat sichern. Neueres geprüftes ZIP ÜBER DENSELBEN ORDNER entpacken,
.classroom-project, Volume und Schlüssel behalten, dann Start verwenden.
Für Updates keinen neuen Ordner kopieren. Bei Quellcode .env, Projekt-/Image-Namen
und Daten behalten.
```

## Acceptance checklist

- Local teacher, student and projector pages respond; the sandbox is available.
- Host-published port binds only to loopback; no existing installation was touched.
- New classroom has a separate project/data volume and explicit checkpoint-only protocol.
- Teacher reads their own key privately; no credential appears in the report.
- Exact version and real checks are recorded. A basic page check is not a race test or hardware-platform certification.
- macOS users run an approved isolated demo before teaching: no fresh Mac hardware acceptance is implied by the prompt.
