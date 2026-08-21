#!/usr/bin/env bash
set -euo pipefail

IMAGE="vpn-deck-awg-builder:local"

echo "==> Building pinned AmneziaWG runtime"
docker build -f infra/Dockerfile -t "$IMAGE" .

mkdir -p ./bin
container_id="$(docker create "$IMAGE")"
trap 'docker rm -f "$container_id" >/dev/null 2>&1 || true' EXIT
docker cp "$container_id:/binaries/." ./bin/
chmod 0755 ./bin/amneziawg-go ./bin/awg ./bin/awg-quick

echo "==> Runtime extracted to ./bin/"
ls -lh ./bin/
cat ./bin/versions.json
