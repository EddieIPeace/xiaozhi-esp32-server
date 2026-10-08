#!/usr/bin/env bash
# Eddie-fork: replace the xiaozhi-esp32-server image on the deploy host.
# Intended to be copied over SSH by .github/workflows/eddie-server-deploy.yml.
# Does not touch Caddy, host ports other than the compose file's existing
# mappings, or data/.config.yaml.
set -euo pipefail

NEW_IMAGE="${1:?new image ref required}"
COMPOSE_DIR="${2:?compose directory required}"
GHCR_USER="${3:-eddieipeace}"
CONTAINER_NAME="xiaozhi-esp32-server"
HEALTH_URL="http://127.0.0.1:8003/xiaozhi/ota/"
HEALTH_TRIES="${HEALTH_TRIES:-36}"
HEALTH_SLEEP="${HEALTH_SLEEP:-5}"

if [[ ! -d "${COMPOSE_DIR}" ]]; then
  echo "compose directory not found: ${COMPOSE_DIR}" >&2
  exit 1
fi

cd "${COMPOSE_DIR}"

if [[ ! -f docker-compose.yml ]]; then
  echo "docker-compose.yml not found in ${COMPOSE_DIR}" >&2
  exit 1
fi

logout_ghcr() {
  docker logout ghcr.io >/dev/null 2>&1 || true
}
trap logout_ghcr EXIT

if [[ -n "${GHCR_TOKEN:-}" ]]; then
  printf '%s' "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USER}" --password-stdin
fi

backup="docker-compose.yml.bak"
cp -a docker-compose.yml "${backup}"

restore_compose() {
  if [[ -f "${backup}" ]]; then
    cp -a "${backup}" docker-compose.yml
  fi
}

update_image() {
  local compose_file="$1"
  local image="$2"
  python3 - "${compose_file}" "${image}" <<'PY'
import re
import sys

path, image = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
new, n = re.subn(r"(?m)^(\s*image:\s*)\S+", rf"\g<1>{image}", text, count=1)
if n != 1:
    sys.exit(f"expected to replace exactly 1 image: line, replaced {n}")
open(path, "w", encoding="utf-8").write(new)
PY
}

health_ok() {
  local running
  running="$(docker inspect -f '{{.State.Running}}' "${CONTAINER_NAME}" 2>/dev/null || true)"
  if [[ "${running}" != "true" ]]; then
    return 1
  fi
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "${HEALTH_URL}" || true)"
  [[ "${code}" == "200" ]]
}

wait_healthy() {
  local i
  for ((i = 1; i <= HEALTH_TRIES; i++)); do
    if health_ok; then
      echo "health check passed on attempt ${i}"
      return 0
    fi
    echo "health check attempt ${i}/${HEALTH_TRIES} failed, retrying in ${HEALTH_SLEEP}s"
    sleep "${HEALTH_SLEEP}"
  done
  return 1
}

rollback() {
  echo "deploy failed, rolling back to previous compose image" >&2
  restore_compose
  docker compose up -d
  if ! wait_healthy; then
    echo "rollback health check failed" >&2
    docker ps --filter "name=${CONTAINER_NAME}" || true
    docker logs --tail 80 "${CONTAINER_NAME}" || true
    exit 1
  fi
  echo "rollback succeeded"
  exit 1
}

update_image docker-compose.yml "${NEW_IMAGE}"

if ! docker compose pull; then
  echo "docker compose pull failed" >&2
  rollback
fi

if ! docker compose up -d; then
  echo "docker compose up failed" >&2
  rollback
fi

if ! wait_healthy; then
  echo "new image health check failed" >&2
  docker ps --filter "name=${CONTAINER_NAME}" || true
  docker logs --tail 80 "${CONTAINER_NAME}" || true
  rollback
fi

echo "deployed ${NEW_IMAGE}"
