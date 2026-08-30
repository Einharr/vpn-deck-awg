"""Shared helpers used across vpn_deck modules."""

import os
from typing import Dict


_WG_DAEMON_INTERNAL_ENV = (
    "WG_TUN_FD",
    "WG_UAPI_FD",
    "WG_PROCESS_FOREGROUND",
)


def clean_env() -> Dict[str, str]:
    """Return a safe environment for system networking commands.

    Decky bundles the plugin runtime via PyInstaller, which may inject
    /tmp/_MEI* into LD_LIBRARY_PATH. Child processes like `awg-quick`,
    `ping`, and `curl` must not inherit those paths or they can pick up
    bundled libraries that conflict with SteamOS.

    The WG_* variables are private hand-off variables used when
    amneziawg-go re-execs itself as its foreground daemon child. They must
    never leak from Decky's environment into a fresh awg-quick invocation;
    WG_PROCESS_FOREGROUND=1 would make `amneziawg-go INTERFACE` block instead
    of daemonizing.
    """
    env = os.environ.copy()

    if "LD_LIBRARY_PATH" in env:
        paths = [
            p for p in env["LD_LIBRARY_PATH"].split(":")
            if "/tmp/" not in p and "_MEI" not in p
        ]
        if paths:
            env["LD_LIBRARY_PATH"] = ":".join(paths)
        else:
            del env["LD_LIBRARY_PATH"]

    for key in _WG_DAEMON_INTERNAL_ENV:
        env.pop(key, None)

    return env
