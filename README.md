# VPN Deck AWG

A Decky Loader VPN manager for Steam Deck Game Mode. This fork keeps the simple
`awg-quick` lifecycle of the original `MrWaip/vpn-deck`, but rebuilds the
runtime, profile model and UI around current AmneziaWG.

## Protocol support

The bundled userspace runtime is pinned to **amneziawg-go v3.0.3** and
**amneziawg-tools v3.0.20260730**. One runtime accepts standard WireGuard and
older AmneziaWG configuration generations, so the plugin detects and labels:

- WireGuard
- AmneziaWG 1.0
- AmneziaWG 1.5
- AmneziaWG 2.0
- AmneziaWG 3.0

Detection is informational: imported configs are preserved rather than
converted. Unknown future keys are not stripped by the plugin.

## What changed in 3.x

- New Game Mode UI focused on connection state and VPN profiles.
- Config inspection before import, including protocol, endpoint and routing.
- Safe profile metadata: private/preshared keys are never included in dashboard data.
- Exclusive mode to switch between managed VPNs without route conflicts.
- Persistent Decky settings storage and copy-only migration of legacy configs.
- Runtime health/version reporting and awg-quick log viewer.
- Neutral internet/DNS/HTTPS diagnostics.
- Reproducible AWG runtime build from pinned upstream tags.
- SteamOS `resolvectl` adaptation plus the original endpoint underlay-route fix.
- Automated Python and frontend CI.

## Build

```bash
pnpm install
pnpm build
just test
just build-binaries
just build-plugin
```

`build-binaries` builds `infra/Dockerfile` locally and extracts
`amneziawg-go`, `awg`, patched `awg-quick`, and `versions.json` into `bin/`.

## Config storage

Profiles are stored under Decky's persistent plugin settings directory and
linked into `/etc/amnezia/amneziawg/` while active management is available.
On first run the plugin copies legacy profiles from the old vpn-deck location
when present. SteamOS updates may wipe `/etc`; the links are repaired on plugin
startup by default.

## Notes

The plugin runs with Decky's `root` flag because creating network interfaces,
routes and `/etc/amnezia/amneziawg` links requires elevated privileges.

Original project: `MrWaip/vpn-deck`. See `LICENSE` for redistribution terms.
