import os
from datetime import datetime, timezone
from ipaddress import ip_address
from typing import Iterable, Optional


TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def env_bool(
    name: str,
    default: bool,
    truthy_values: Optional[Iterable[str]] = None,
) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    values = TRUTHY_ENV_VALUES if truthy_values is None else frozenset(truthy_values)
    return raw.strip().lower() in values


def env_int(
    name: str,
    default: int,
    minimum: int = 0,
    *,
    clamp_default: bool = False,
) -> int:
    raw = os.getenv(name)
    fallback = max(minimum, default) if clamp_default else default
    if raw is None:
        return fallback
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return fallback
    return max(minimum, value)


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_loopback_hostname(
    value: Optional[str],
    loopback_hosts: Optional[Iterable[str]] = None,
) -> bool:
    if not value:
        return False
    hostname = str(value).strip().lower()
    if not hostname:
        return False
    if hostname.startswith("["):
        closing = hostname.find("]")
        if closing != -1:
            suffix = hostname[closing + 1 :]
            if not suffix or (
                suffix.startswith(":") and suffix[1:].isdigit()
            ):
                hostname = hostname[1:closing]
    if ":" in hostname and hostname.count(":") == 1 and hostname.rsplit(":", 1)[1].isdigit():
        hostname = hostname.rsplit(":", 1)[0]
    hosts = LOOPBACK_HOSTS if loopback_hosts is None else frozenset(loopback_hosts)
    if hostname in hosts:
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False
