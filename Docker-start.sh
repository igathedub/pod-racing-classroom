#!/bin/sh
# Run from any directory; no host Python, uv, Node or npm needed.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! docker compose version >/dev/null 2>&1; then
  printf '%s\n' 'Install Docker with the Compose plugin and start its Linux daemon.' >&2
  exit 1
fi
docker compose up --build -d --wait --wait-timeout 180
binding=$(docker compose port classroom 8765)
port=${binding##*:}
printf '\nTeacher: http://localhost:%s/teacher\n' "$port"
printf 'Projector: http://localhost:%s/projector\n' "$port"
printf '%s\n' 'Keep the teacher token below private. Containers keep running after this window closes.'
docker compose logs --tail 30 classroom
