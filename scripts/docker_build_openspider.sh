#!/usr/bin/env bash
# Build OpenSpider Docker image (includes console frontend build in multi-stage).
# Run from repo root: bash scripts/docker_build_openspider.sh [IMAGE_TAG] [EXTRA_ARGS...]
# Example: bash scripts/docker_build_openspider.sh openspider:latest
#          bash scripts/docker_build_openspider.sh myreg/openspider:v1 --no-cache
#
# By default the Docker image excludes imessage (macOS-only).
# Override via:
#   OPENSPIDER_DISABLED_CHANNELS=imessage,voice bash scripts/docker_build_openspider.sh
#   OPENSPIDER_ENABLED_CHANNELS=discord,telegram  bash scripts/docker_build_openspider.sh
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DOCKERFILE="${DOCKERFILE:-$REPO_ROOT/deploy/Dockerfile.openspider}"
TAG="${1:-openspider:latest}"
shift || true

# Channels to exclude from the image (default: imessage).
DISABLED_CHANNELS="${OPENSPIDER_DISABLED_CHANNELS:-imessage}"

echo "[docker_build_openspider] Building image: $TAG (Dockerfile: $DOCKERFILE)"
docker build -f "$DOCKERFILE" \
    --build-arg OPENSPIDER_DISABLED_CHANNELS="$DISABLED_CHANNELS" \
    ${OPENSPIDER_ENABLED_CHANNELS:+--build-arg OPENSPIDER_ENABLED_CHANNELS="$OPENSPIDER_ENABLED_CHANNELS"} \
    -t "$TAG" "$@" .
echo "[docker_build_openspider] Done."
echo "[docker_build_openspider] OpenSpider app port: 8088 (default). Override with -e OPENSPIDER_PORT=<port>."
echo "[docker_build_openspider] Run:     docker run -p 127.0.0.1:8088:8088 $TAG"
echo "[docker_build_openspider] Compose: docker compose -f docker-compose.openspider.yml up -d"
