# Show available recipes
default:
    @just --list

install:
    pnpm install

test:
    PYTHONPATH=py_modules python3 -m unittest -v test_protocol.py test_unit.py test_plugin_smoke.py

build-ui:
    pnpm build

# Runs the core tests inside the target SteamOS base image.
test-smoke:
    bash infra/test-smoke.sh

# Reproducibly build pinned AWG3-compatible binaries and patched awg-quick.
build-binaries:
    bash infra/extract-binaries.sh

build-plugin:
    bash infra/build-plugin.sh

release bump="patch":
    pnpm release:{{ bump }}
