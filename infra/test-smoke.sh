#!/usr/bin/env bash
set -euo pipefail

IMAGE="ghcr.io/steamdeckhomebrew/holo-base:latest"

echo "==> Running core tests in ${IMAGE}"
docker run --rm \
    --platform linux/amd64 \
    -v "$(pwd):/plugin:ro" \
    -w /plugin \
    "$IMAGE" \
    bash -c "PYTHONPATH=py_modules python3 -m unittest -v test_protocol.py test_unit.py test_plugin_smoke.py"
