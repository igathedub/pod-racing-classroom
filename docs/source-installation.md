# Advanced: source installation / Quellcodeinstallation

Docker with Compose v2 is required. Do not apply source settings to the runtime ZIP or overwrite an existing installation.

## English

For development or explicit configuration, download the source archive for the [v1.0.0 tag](https://github.com/igathedub/pod-racing-classroom/releases/tag/v1.0.0), or clone and check out that tag. This builds locally; it is not the prebuilt runtime ZIP. Normal users should follow the [release quickstart](../README.md).

For **source installations only**, in a **new installation folder**, create `.env` beside the root `compose.yaml`:

```dotenv
COMPOSE_PROJECT_NAME=pod-classroom-my-workshop
POD_BOT_IMAGE=pod-classroom-bot:my-workshop
POD_INPUT_PROTOCOL=checkpoint-only
POD_BIND=127.0.0.1
POD_PORT=8765
```

Choose a unique project name and local `POD_BOT_IMAGE` tag per independent source installation, so one build cannot replace another classroom's sandbox image. Do **not** apply this fresh-install example over an existing deployment's configuration. Source Compose defaults to the older `legacy` protocol unless explicitly configured; the setting above selects the new one-line starter without modifying saved bots.

- **Windows:** double-click **`Docker-start.cmd`**.
- **macOS/Linux:** run **`sh Docker-start.sh`**.

These existing source launchers build the app and sandbox images, wait for health and display local logs. Then open http://localhost:8765/teacher or http://localhost:8765/projector. Equivalent **source-only** commands from that folder:

```sh
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
docker compose logs classroom
```

Each fresh data installation generates its **own random teacher key** and persists it. There is no shared/default password. In a **source installation**, the key appears in local app logs; recover it with `docker compose logs classroom`. In the **ZIP**, Start saves those logs privately to `teacher-private.log`. Never delete data to recover a key or share unredacted logs.

### Stop and restart (source only)

Run commands from the same installation folder with the **same Compose project name and configuration**:

```sh
docker compose stop
docker compose start
docker compose ps
```

Retain `.env`, project name, unique bot image tag, data volume and teacher key when updating. After a private full-volume backup and review, use `docker compose up --build -d`. After `docker compose down` (without volume deletion), use `docker compose up -d` instead of `start`. Interrupted jobs fail rather than resume.

## Deutsch

Für Entwicklung oder bewusste Konfiguration das Quellcodearchiv des [Tags v1.0.0](https://github.com/igathedub/pod-racing-classroom/releases/tag/v1.0.0) laden oder diesen Tag auschecken. Dieser Weg baut lokal; er ist nicht das fertige Runtime-ZIP. Für den normalen Einstieg den [Release-Schnellstart](../README.de.md) verwenden.

**Nur für Quellcodeinstallationen:** Für eine **neue Installation** neben der Root-`compose.yaml` eine `.env` anlegen:

```dotenv
COMPOSE_PROJECT_NAME=pod-classroom-mein-workshop
POD_BOT_IMAGE=pod-classroom-bot:mein-workshop
POD_INPUT_PROTOCOL=checkpoint-only
POD_BIND=127.0.0.1
POD_PORT=8765
```

Jede unabhängige Quellcodeinstallation benötigt einen eigenen Projektnamen und einen eindeutigen lokalen `POD_BOT_IMAGE`-Tag, damit ihr Build kein Sandbox-Image einer anderen Klasse ersetzt. **Vorhandene Deployment-Konfiguration damit nicht überschreiben.** Ohne explizite Einstellung verwendet Source-Compose noch `legacy`. Das Beispiel wählt den neuen Einzeilen-Startcode; gespeicherte Bots werden nicht umgeschrieben.

- **Windows:** **`Docker-start.cmd`** doppelklicken.
- **macOS/Linux:** **`sh Docker-start.sh`** ausführen.

Diese vorhandenen Quellcode-Starter bauen App und Sandbox, warten auf Betriebsbereitschaft und zeigen lokale Logs. Anschließend http://localhost:8765/teacher oder http://localhost:8765/projector öffnen. Gleichwertige Befehle **nur für Quellcodeinstallationen** im Installationsordner:

```sh
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
docker compose logs classroom
```

Jede neue Dateninstallation erzeugt einen **eigenen zufälligen Lehrkraft-Schlüssel** und speichert ihn dauerhaft. Es gibt kein gemeinsames Standardpasswort. **Quellcodeinstallation:** Schlüssel in lokalen App-Logs mit `docker compose logs classroom` lesen. **ZIP:** Start speichert diese Logs privat in `teacher-private.log`. Niemals zur Schlüsselwiederherstellung Daten löschen oder ungeschwärzte Logs teilen.

### Stoppen und neu starten (nur Quellcode)

Im selben Installationsordner mit **demselben Compose-Projektnamen und derselben Konfiguration**:

```sh
docker compose stop
docker compose start
docker compose ps
```

Bei Updates `.env`, Projektnamen, eindeutigen Bot-Image-Tag, Datenvolume und Lehrkraft-Schlüssel erhalten. Nach privatem vollständigem Volume-Backup und Prüfung mit `docker compose up --build -d` aktualisieren. Nach `docker compose down` (ohne Volume-Löschung) ist `docker compose up -d` statt `start` nötig. Unterbrochene Aufträge werden nicht fortgesetzt.

## LAN and Docker configuration / LAN und Docker

Default binding is **`127.0.0.1:8765`**, accessible only on the host. Nothing in this guide automatically opens a firewall, creates a tunnel or changes an existing live deployment.

For a trusted classroom LAN **using a source installation only**, agree the change with school IT, then explicitly set `POD_BIND=0.0.0.0` in **this installation's** `.env` and recreate its service with `docker compose up -d`. Share the host's private LAN IP, not a Docker/VPN address. Limit firewall access to the private local subnet and test from a second device; guest Wi-Fi may block peers. Linux Docker port publishing may bypass some host-firewall rules: verify actual exposure. Restore `POD_BIND=127.0.0.1` and recreate to return to local-only use. An occupied port can be changed with `POD_PORT`, updating all URLs accordingly.

Optional classroom invitations admit up to **100 participant sessions**, including projector browsers. They use expiring shared codes and cookies, not individual identity or abuse-proof admission. HTTPS is required for default Secure cookies. Invitations and rate limits **do not make anonymous public code execution safe**. See [Security](../SECURITY.md).


Standard ist **`127.0.0.1:8765`**, nur auf dem Gastgeber erreichbar. Diese Anleitung öffnet keine Firewall, legt keinen Tunnel an und ändert keine laufende Installation automatisch.

Für ein vertrauenswürdiges Unterrichts-LAN **nur bei einer Quellcodeinstallation** mit der Schul-IT abstimmen, dann in der `.env` **dieser Installation** ausdrücklich `POD_BIND=0.0.0.0` setzen und mit `docker compose up -d` neu erstellen. Die private LAN-IP des Hosts teilen, keine Docker-/VPN-Adresse. Firewall auf das private lokale Subnetz beschränken und mit zweitem Gerät testen; Gäste-WLAN kann Verbindungen sperren. Docker unter Linux kann manche Host-Firewall-Regeln umgehen: tatsächliche Erreichbarkeit prüfen. Zur Rückkehr `POD_BIND=127.0.0.1` setzen und neu erstellen. Bei belegtem Port `POD_PORT` ändern und URLs entsprechend anpassen.

Optionale Klasseneinladungen erlauben **100 Teilnahmesitzungen**, einschließlich Beamer-Browsern. Zeitlich begrenzte gemeinsame Codes und Cookies sind keine persönliche Identität oder missbrauchssichere Zulassung. Standardmäßige Secure-Cookies benötigen HTTPS. Einladungen und Ratenlimits machen **anonyme öffentliche Codeausführung nicht sicher**. Siehe [Sicherheit](../SECURITY.md).


For source installations, rootless Linux needs the real socket in `POD_DOCKER_SOCKET` and a host Compose client targeting that same daemon. Remote Docker contexts are not the standard supported setup; rootless resource limits depend on cgroup support. Do not guess a socket path or reuse a Windows `npipe://` endpoint inside Linux containers.

Bei Quellcodeinstallationen benötigt Rootless Linux den tatsächlichen Socket in `POD_DOCKER_SOCKET` und einen Compose-Client am selben Daemon. Remote-Kontexte sind nicht der Standardfall; Ressourcenlimits hängen von cgroups ab. Keine Socket-Pfade raten oder Windows-`npipe://` in Linux-Container übernehmen.

### Optional class access / Optionaler Klassenzugang

For a separately approved **source deployment**, `POD_CLASS_ACCESS_REQUIRED=1` requires a teacher-issued expiring invitation and participant cookie, including for projector browsers. Default is `0`; do not silently change an existing classroom's access mode. `POD_CLASS_COOKIE_SECURE=1` is the default and requires browser HTTPS. Teacher authorization and submission ownership remain separate. Rotation/revocation invalidates participant sessions; the cap is 100 sessions. Invitation expiry does not change the submission deadline. Check actual access after an approved recreate, not just the `.env` text.

Nur bei separat genehmigtem **Quellcode-Deployment** verlangt `POD_CLASS_ACCESS_REQUIRED=1` eine zeitlich begrenzte Lehrkraft-Einladung und ein Teilnehmercookie, auch beim Beamer. Standard ist `0`; Zugangsschutz vorhandener Klassen nicht still ändern. `POD_CLASS_COOKIE_SECURE=1` ist voreingestellt und benötigt Browser-HTTPS. Lehrkraftberechtigung und Abgabebesitz bleiben getrennt. Rotation/Widerruf macht Teilnahmesitzungen ungültig; maximal 100 Sitzungen. Einladungsgültigkeit ändert nicht die Abgabefrist. Nach genehmigtem Recreate tatsächlichen Zugang prüfen, nicht nur `.env` lesen.

Neither invitations nor rate limits authorize anonymous public code execution. Independent isolation and ingress review are still required; see [SECURITY.md](../SECURITY.md) and [operator security preparation](../SECURITY_PREPARATION.md).
