"""Small helpers for constructing safe-to-print tc netem commands."""

from __future__ import annotations

import shlex


def netem_replace(interface: str, line: str) -> str:
    """Return the requested qdisc replace command for an impairment line."""
    if not interface or any(c.isspace() for c in interface):
        raise ValueError("interface must be a nonempty interface name")
    line = line.strip()
    if line.startswith("netem "):
        line = line[6:]
    if any(c in line for c in "\n\r;|&`$"):
        raise ValueError("netem line contains shell metacharacters")
    return f"tc qdisc replace dev {shlex.quote(interface)} root netem{(' ' + line) if line else ''}"


def netem_remove(interface: str) -> str:
    if not interface or any(c.isspace() for c in interface):
        raise ValueError("interface must be a nonempty interface name")
    return f"tc qdisc del dev {shlex.quote(interface)} root 2>/dev/null || true"
