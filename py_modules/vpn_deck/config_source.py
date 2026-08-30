"""Normalize VPN config sources into an awg-quick compatible .conf.

Besides plain WireGuard/AmneziaWG INI files, Amnezia commonly distributes
profiles as ``vpn://`` links. Those links contain URL-safe base64 data which
is usually Qt qCompress output (4-byte uncompressed length + zlib stream)
wrapping JSON. AWG3-only values can live as separate fields next to an
embedded legacy ``config`` string, so they must be merged back into the
[Interface] section before handing the profile to awg-tools.
"""

from __future__ import annotations

import base64
import json
import re
import zlib
from typing import Any, Dict, Iterable, Optional


SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
KEY_RE = re.compile(r"^\s*([^=]+?)\s*=")
INTERFACE_SECTION_RE = re.compile(r"^\s*\[interface\]\s*$", re.IGNORECASE | re.MULTILINE)
PEER_SECTION_RE = re.compile(r"^\s*\[peer\]\s*$", re.IGNORECASE | re.MULTILINE)

# Normalized JSON key -> canonical awg-quick config key.
AWG_FIELDS = {
    "jc": "Jc",
    "jmin": "Jmin",
    "jmax": "Jmax",
    "s1": "S1",
    "s2": "S2",
    "s3": "S3",
    "s4": "S4",
    "h1": "H1",
    "h2": "H2",
    "h3": "H3",
    "h4": "H4",
    "i1": "I1",
    "i2": "I2",
    "i3": "I3",
    "i4": "I4",
    "i5": "I5",
    "headerprotectionkey": "HeaderProtectionKey",
    "contentpaddingaddition": "ContentPaddingAddition",
    "rekeyaftertime": "RekeyAfterTime",
    "rekeytimeout": "RekeyTimeout",
    "rejectaftertime": "RejectAfterTime",
    "keepalivetimeout": "KeepaliveTimeout",
    "maxhandshakeattempts": "MaxHandshakeAttempts",
}


def _normalise_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _looks_like_conf(text: str) -> bool:
    # Do not use substring checks here: JSON/vpn payloads often contain an
    # escaped embedded config string, which includes the literal words
    # "[Interface]" and "[Peer]" but not real INI section lines.
    return bool(INTERFACE_SECTION_RE.search(text) and PEER_SECTION_RE.search(text))


def _walk(value: Any, depth: int = 0) -> Iterable[Any]:
    """Walk JSON and JSON-encoded strings with a conservative depth limit."""
    if depth > 10:
        return
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child, depth + 1)
    elif isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                decoded = json.loads(stripped)
            except (TypeError, ValueError):
                return
            yield from _walk(decoded, depth + 1)


def _decode_vpn_link(text: str) -> Any:
    payload = text.strip()
    if not payload.lower().startswith("vpn://"):
        raise ValueError("Not an Amnezia vpn:// payload")
    encoded = payload[6:].strip()
    if not encoded:
        raise ValueError("Empty Amnezia vpn:// payload")

    encoded += "=" * ((4 - len(encoded) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
    except Exception as exc:
        raise ValueError(f"Invalid vpn:// base64: {exc}") from exc

    candidates = []
    # Qt qCompress stores an unsigned 32-bit uncompressed length before zlib.
    if len(raw) > 4:
        try:
            candidates.append(zlib.decompress(raw[4:]))
        except zlib.error:
            pass
    try:
        candidates.append(zlib.decompress(raw))
    except zlib.error:
        pass
    candidates.append(raw)

    for candidate in candidates:
        try:
            return json.loads(candidate.decode("utf-8-sig"))
        except (UnicodeError, ValueError):
            continue
    raise ValueError("vpn:// payload did not contain Amnezia JSON")


def _find_embedded_conf(root: Any) -> Optional[str]:
    candidates = []
    for item in _walk(root):
        if isinstance(item, dict):
            for key, value in item.items():
                if not isinstance(value, str) or not _looks_like_conf(value):
                    continue
                normalized = _normalise_key(key)
                score = 3 if normalized == "config" else 2 if normalized == "nativeconfig" else 1
                candidates.append((score, value))
        elif isinstance(item, str) and _looks_like_conf(item):
            candidates.append((0, item))
    return max(candidates, default=(None, None), key=lambda pair: pair[0])[1]


def _collect_awg_fields(root: Any) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for item in _walk(root):
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            canonical = AWG_FIELDS.get(_normalise_key(key))
            if not canonical or isinstance(value, (dict, list, bool)) or value is None:
                continue
            rendered = str(value).strip()
            if rendered:
                values.setdefault(canonical, rendered)
    return values


def _inject_interface_fields(conf: str, fields: Dict[str, str]) -> str:
    if not fields:
        return conf.rstrip() + "\n"

    lines = conf.splitlines()
    interface_index = next(
        (index for index, line in enumerate(lines) if line.strip().lower() == "[interface]"),
        None,
    )
    if interface_index is None:
        return conf.rstrip() + "\n"

    next_section = len(lines)
    for index in range(interface_index + 1, len(lines)):
        if SECTION_RE.match(lines[index]):
            next_section = index
            break

    present = set()
    for line in lines[interface_index + 1:next_section]:
        match = KEY_RE.match(line)
        if match:
            present.add(_normalise_key(match.group(1)))

    additions = [
        f"{canonical} = {value}"
        for canonical, value in fields.items()
        if _normalise_key(canonical) not in present
    ]
    if additions:
        lines[next_section:next_section] = additions + [""]
    return "\n".join(lines).rstrip() + "\n"


def normalize_config_source(text: str) -> Dict[str, Any]:
    """Return normalized config content and source metadata.

    No key material is included in errors/warnings; the normalized content is
    intended only for internal storage and is never returned to the dashboard.
    """
    raw = (text or "").lstrip("\ufeff").strip()
    if not raw:
        return {"success": False, "error": "Config file is empty", "format": "empty"}

    if _looks_like_conf(raw):
        return {"success": True, "content": raw.rstrip() + "\n", "format": "conf", "warnings": []}

    root: Any
    source_format: str
    try:
        if raw.lower().startswith("vpn://"):
            root = _decode_vpn_link(raw)
            source_format = "amnezia-vpn-link"
        elif raw.startswith(("{", "[")):
            root = json.loads(raw)
            source_format = "amnezia-json"
        else:
            return {
                "success": False,
                "error": "File is neither a WireGuard/AmneziaWG .conf nor an Amnezia vpn:// profile",
                "format": "unknown",
            }
    except (TypeError, ValueError) as exc:
        return {"success": False, "error": str(exc), "format": "unknown"}

    conf = _find_embedded_conf(root)
    if not conf:
        return {
            "success": False,
            "error": "Amnezia profile does not contain an embedded WireGuard/AmneziaWG config",
            "format": source_format,
        }

    fields = _collect_awg_fields(root)
    normalized = _inject_interface_fields(conf, fields)
    injected_awg3 = [
        key for key in (
            "HeaderProtectionKey", "ContentPaddingAddition", "RekeyAfterTime",
            "RekeyTimeout", "RejectAfterTime", "KeepaliveTimeout", "MaxHandshakeAttempts",
        )
        if _normalise_key(key) in {_normalise_key(item) for item in fields}
    ]
    warnings = []
    if injected_awg3:
        warnings.append("AWG3 parameters restored from Amnezia profile metadata")

    return {
        "success": True,
        "content": normalized,
        "format": source_format,
        "warnings": warnings,
    }
