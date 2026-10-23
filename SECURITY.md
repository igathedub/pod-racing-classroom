# Security policy

## Intended use and trust boundaries

Pod Racing Classroom is a local or explicitly approved **trusted private-LAN** teaching application, not a turnkey anonymous public code-execution service. English/German quickstarts: [README.md](README.md), [README.de.md](README.de.md).

- Student programs execute only in restricted Docker containers: no network, Docker socket or host mounts; non-root, read-only filesystem, dropped capabilities, resource/output limits. Missing sandbox support must fail closed.
- **The trusted application mounts the Docker socket and therefore has host-admin-equivalent capability.** A read-only socket does not remove that capability. A compromised app can compromise the Docker host.
- Docker shares a kernel boundary and is not a guarantee against runtime/kernel vulnerabilities. Keep Docker and the host patched. Use dedicated disposable isolation for hostile code; a classroom invitation is not a substitute.
- Default binding is localhost (`127.0.0.1`). LAN access needs explicit operator/IT approval. Do not add port forwarding, tunnels, firewall changes or an internet endpoint as an automatic setup step.
- Optional invitation codes are shared, expiring classroom access, not verified individual identity. Rate limits are not distributed denial-of-service protection. HTTPS, edge/origin protection and independent execution-isolation review remain necessary for any internet-facing design.
- Use one app process/worker. Keep data volumes, backups and logs private. Teacher secrets are generated per fresh data installation; do not reuse another classroom's key. Do not post secrets, student code or raw databases to issues.

## Reporting a vulnerability privately

**Do not post exploit details, credentials or student data in public issues or pull requests.**

Use [GitHub's private vulnerability reporting form](https://github.com/igathedub/pod-racing-classroom/security/advisories/new) (**Security → Advisories → Report a vulnerability**). Private reporting was enabled and read back through GitHub's API when this policy was prepared. You may need to sign in to GitHub.

If that form becomes unavailable and you do not already have a trusted private channel to the maintainer, open a minimal public issue asking **only** for a private security contact or restoration of private reporting. Do not include the affected endpoint, exploit, logs, tokens or other sensitive details. Wait for a private channel before sharing the report. No private email address is advertised here.

A private report should include the affected commit/release, OS/Docker version, expected versus actual security boundary, minimal reproduction on synthetic data, and impact. Redact all credentials. Do not test against someone else's classroom or a live teaching deployment. Coordinate public disclosure with the maintainer after a fix is available.

## Supported versions and updates

This project does not yet publish a long-term-support or security-response-time guarantee. Use the latest reviewed stable release once published, read release notes and verify actual image availability. Before the first stable publication, identify an exact source commit rather than calling a branch a release. No response or fix deadline is guaranteed.

Updates must preserve the existing project name, private configuration, teacher key and data volume. Back up privately and stop active jobs first. Never use volume prune, reset or `down --volumes` as a security update. Do not silently change the input protocol or access policy of an existing class.

## Deutsch — Kurzfassung

Nur lokal oder im ausdrücklich freigegebenen vertrauenswürdigen LAN betreiben. Die App besitzt über den Docker-Socket faktisch Host-Adminrechte; Bots dürfen ihn niemals erhalten. Docker, Einladungen und Ratenlimits machen anonymen Internetbetrieb nicht sicher. Keine Zugangsdaten, Schülerdaten oder Exploitdetails öffentlich melden. Falls GitHubs privates Meldeformular fehlt, öffentlich **nur** um einen privaten Kontakt beziehungsweise dessen Freischaltung bitten und Details erst privat übermitteln. Updates dürfen Daten, Schlüssel und bestehende Zugangseinstellungen nicht zurücksetzen.
