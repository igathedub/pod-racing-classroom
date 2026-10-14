# Optional whole-site password gate

This is a small, shared-password alternative to Cloudflare Access, not an identity
system. Initial use is **teacher-only**. Default website username: `igor`.
**Do not share these Basic credentials with students**: they grant entry to the
whole classroom website and its read surfaces (subject to the independent class
access setting), not just a student landing page. Opening to students later needs
an explicit access review and controlled invitation policy.

Basic login never grants teacher/admin privileges. The separate `X-Admin-Token`
is still required for admin operations. `POD_CLASS_ACCESS_REQUIRED` and classroom
invitation cookies remain independent; this override does not change their values.
The proxy removes `Authorization` upstream, while preserving `X-Admin-Token`,
`Host`, request cookies and response `Set-Cookie`. Every path is gated, including
`/`, assets, health, API, `/teacher` and `/projector`; there is no public health bypass.
The application's internal Docker healthcheck still works without passing through
Caddy.

## Mandatory ingress boundary

```text
browser -- HTTPS --> Cloudflare edge -- encrypted Tunnel --> Windows cloudflared
        -- loopback HTTP 127.0.0.1:8766 --> Caddy -- Docker HTTP --> classroom:8765
```

- Require HTTPS at the Cloudflare edge (HTTP-to-HTTPS redirect, preferably HSTS).
  Never send Basic credentials over external HTTP, and never create an alternate
  public HTTP route or a route directly to port 8765.
- Configure the Tunnel's service URL **only** as `http://127.0.0.1:8766`. There is no
  TLS certificate or HTTPS validation bypass needed on this local HTTP hop.
  Do not set `noTLSVerify` to make an external HTTPS route work.
- Caddy intentionally disables automatic HTTPS and its admin endpoint. Port 8766
  is loopback-only; the override explicitly removes classroom host ports using
  `!reset []`. Do not combine with a later override that restores backend ports.
- **Disable/remove the public tunnel route before setup, changes, failures or
  rollback.** Keep it disabled if validation, authenticated checks, restart checks,
  host/origin checks or encrypted-edge checks fail. Never bypass the gate to restore
  service. Stop the route before stopping the gate.
- Set `POD_PUBLIC_ORIGINS` to the exact public HTTPS origin and
  `POD_ALLOWED_HOSTS` to its hostname using the existing application settings.
  Keep secure classroom cookies enabled for public HTTPS.

## Private password and hash

Use a unique high-entropy password. Keep the password in a private password manager
and the Argon2id hash in an owner-only ACL-protected file **outside this repository**.
Do not put either in Git, the Caddyfile, a repository `.env`, command arguments,
logs, screenshots, shell history or support transcripts. Treat the hash as private:
Docker administrators can inspect container environment variables.

Pinned official image:

```text
caddy:2.11.6-alpine@sha256:d44355d3c2149dc580ce2cac735955d1c08d3d00882c30489c241aa51a5c10d9
```

Caddy accepts hashed passwords only. Generate with `caddy hash-password --algorithm
argon2id`, supplying the password via STDIN, not `--plaintext`. For Windows Python,
use a **binary** subprocess input with an LF terminator: text-mode CRLF conversion
can inadvertently include a carriage return in the password being hashed.
For example, in a trusted local Python session (never paste the password in code):

```python
import getpass
import subprocess
from pathlib import Path

image = "caddy:2.11.6-alpine@sha256:d44355d3c2149dc580ce2cac735955d1c08d3d00882c30489c241aa51a5c10d9"
# Choose an existing owner-only ACL-protected directory outside the repository.
output = Path.home() / "private-pod" / "password-gate.env"
password = getpass.getpass("Unique website password: ")
result = subprocess.run(
    ["docker", "run", "--rm", "-i", "--cpus", "0.25", "--memory", "192m",
     "-e", "GOMAXPROCS=1", image, "caddy", "hash-password", "--algorithm", "argon2id"],
    input=(password + "\n").encode("utf-8"), capture_output=True, check=True,
)
hashed = result.stdout.decode("utf-8").strip()
if not hashed.startswith("$argon2id$"):
    raise RuntimeError("Unexpected password hash format")
# Exclusive creation avoids accidentally overwriting existing private settings.
with output.open("x", encoding="utf-8", newline="\n") as file:
    file.write("POD_SITE_USER=igor\nPOD_SITE_PASSWORD_HASH='" + hashed + "'\n")
del password, hashed, result
```

Do not print the result. Pre-create and verify the private directory's ACLs before
running this example. Single quotes in the private Compose env file preserve the
hash's dollar signs literally. If using a shell environment instead, preserve the
complete hash exactly; do not accidentally expand `$argon2id` as a shell variable.
Never dump `docker compose config` or `docker inspect` to logs: both can expose the
hash. Missing/empty hash is rejected by Compose; missing/malformed hash is also
rejected by Caddy validation. A mistyped but valid hash needs a positive login test.

## Validate and start (operator-controlled, not automatic deployment)

Use Compose supporting `!reset` (2.24.0+). Run from the existing repository and use
**the same Compose project name/directory as the existing deployment**, so the
existing `classroom-data` volume is reused. Do not copy the project to another
folder and start a second project accidentally. The private env file must also
preserve any deployment-specific host/origin/class-access settings; explicit
`--env-file` replaces implicit repository `.env` loading.

Commands below assume `PRIVATE_ENV` points to the private file and the public
Tunnel route has already been disabled. A secret exported in the shell overrides
an env-file value; avoid stale exported settings.

```sh
docker compose --env-file "$PRIVATE_ENV" -f compose.yaml -f compose.password.yaml config --quiet
docker compose --env-file "$PRIVATE_ENV" -f compose.yaml -f compose.password.yaml run --rm --no-deps password-gate 'cp /usr/bin/caddy /run/caddy; exec /run/caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile'
docker compose --env-file "$PRIVATE_ENV" -f compose.yaml -f compose.password.yaml up -d
```

The gate has a read-only root filesystem and readonly Caddyfile, all capabilities
dropped, no-new-privileges, 0.50 CPU and 192 MiB memory. No Docker socket or admin
volume is mounted into it. The official binary carries a file capability for low
ports; with all capabilities dropped, direct execution returns `operation not
permitted`. Startup copies only that binary to a bounded 64 MiB executable,
`nosuid` RAM filesystem (`/run`) and executes the capability-free copy on port 8080.
No image rebuild or writable persistent application layer is needed. Caddy may log
read-only certificate-storage cleanup warnings; TLS is deliberately off locally
and these do not bypass or disable authentication.

Before adding the public route:

1. Confirm the effective backend has **no published host ports** and the gate's
   only published address is `127.0.0.1:8766`.
2. Verify unauthenticated and wrong-password requests receive 401 on root, assets,
   health, API, teacher and projector. Use `curl -i http://127.0.0.1:8766/health` for
   a credential-free check. For an authenticated check, `curl -u igor ...` prompts
   locally for the password without putting it in command arguments.
3. Verify correct credentials reach the app, using the intended Host header for
   local checks if the application's host allowlist is enabled. Confirm admin
   operations still require their separate teacher token and cookies still work.
4. Restart the gate, then repeat negative **and positive** checks. Browser Basic
   credentials are cached; a fresh client is required for a true negative check.
5. Enable only the encrypted Cloudflare route to the gate; repeat checks at the
   public **HTTPS** hostname. On any unexpected status or bypass, immediately
   disable the public route and investigate offline.

For password rotation: disable the public route, generate a fresh unique password
and hash privately, update the private file, recreate the gate with the same
Compose files, test both old-password rejection and new-password success, then
restore the route. `restart` alone does not reload changed container environment.
For rollback: remove the public route first, keep classroom private, and explicitly
review binding changes before using base Compose alone.
**Never use `down -v`, reset classroom data, or remove/recreate the data volume.**

## Reproducible isolated acceptance

```sh
python -m pytest tests/test_password_gate_config.py -q
POD_GATE_DOCKER_TEST=1 POD_GATE_TEST_STUB_IMAGE=EXISTING_PYTHON_IMAGE python -m pytest tests/test_password_gate_config.py -q --tb=short
```

The optional real test reuses an existing Python-capable image only as a tiny
read-only stub; it does not build/tag images, start the application, attach its
volumes, alter existing containers or deploy the Tunnel. All test containers and
the network have unique names/labels and are removed in `finally`. Caddy and the
stub each use at most 0.25 CPU and 192 MiB. Ephemeral credentials are generated in
memory; the stub records only Authorization **presence**, never its value. The
test checks actual HTTP denials without upstream hits, authenticated forwarding,
headers/cookies, POST protection, missing/invalid hash validation, effective
Compose port reset/volume preservation and password enforcement after restart.
Do not run with pytest `--showlocals`, which can expose in-memory test credentials
on a failure. This stub test does not replace real-app or public HTTPS acceptance.

References: [Caddy basic_auth](https://caddyserver.com/docs/caddyfile/directives/basic_auth),
[Caddy hash-password](https://caddyserver.com/docs/command-line#caddy-hash-password),
[Compose reset](https://docs.docker.com/reference/compose-file/merge/#reset-value),
[official Caddy image](https://hub.docker.com/_/caddy).
