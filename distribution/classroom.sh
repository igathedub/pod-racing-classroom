#!/bin/sh
# No eval, sourced .env, remote daemon, build, or volume deletion.
set -eu
umask 077
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
case ${1:-start} in start|stop) action=${1:-start};; *) echo 'Use start or stop' >&2; exit 1;; esac
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
context=$(docker context show)
endpoint=$(docker context inspect "$context" --format '{{.Endpoints.docker.Host}}')
case "$endpoint" in
  unix:///*) POD_RELEASE_SOCKET=${endpoint#unix://};;
  npipe://*) POD_RELEASE_SOCKET=/var/run/docker.sock;;
  *) echo 'Only local Unix sockets or Docker Desktop are supported; select a local context.' >&2; exit 1;;
esac
export POD_RELEASE_SOCKET
[ "$(docker --context "$context" info --format '{{.OSType}}')" = linux ] || { echo 'Start Docker with Linux containers.' >&2; exit 1; }
docker --context "$context" compose version >/dev/null
if [ ! -e .classroom-project ]; then
  [ "$action" = start ] || { echo 'No saved classroom project.' >&2; exit 1; }
  id=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
  (set -C; printf 'pod-public-%s\n' "$id" > .classroom-project) || exit 1
fi
project=$(cat .classroom-project)
case "$project" in pod-public-*) id=${project#pod-public-};; *) echo 'Invalid project file.' >&2; exit 1;; esac
case "$id" in *[!0-9a-f]*|'') echo 'Invalid project file.' >&2; exit 1;; esac
[ "${#id}" = 32 ] || { echo 'Invalid project file.' >&2; exit 1; }
compose() { docker --context "$context" compose --project-name "$project" --env-file compose.defaults -f compose.yaml "$@"; }
if [ "$action" = stop ]; then
  compose stop
  printf '%s\n' 'Stopped. Classroom data is preserved.'
else
  compose pull
  compose up --no-build -d --wait --wait-timeout 180
  : > teacher-private.log
  chmod 600 teacher-private.log
  compose logs --no-color classroom > teacher-private.log
  printf '%s\n' 'Teacher: http://localhost:8765/teacher' 'Projector: http://localhost:8765/projector' 'Keep teacher-private.log private: it contains the teacher key.'
fi
