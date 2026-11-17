#!/usr/bin/env python3
"""Check CN-T1 RTP sequencing, timestamps, marker bits, SSRC, and RTCP decoding."""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys


def _fields(tshark: str, pcap: Path, decode: list[str], display_filter: str,
            fields: list[str]) -> list[list[str]]:
    command = [tshark, "-n", "-r", str(pcap)]
    for item in decode:
        command.extend(["-d", item])
    command.extend(["-Y", display_filter, "-T", "fields", "-E", "separator=,",
                    "-E", "quote=d"])
    for field in fields:
        command.extend(["-e", field])
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=True)
    return list(csv.reader(io.StringIO(result.stdout)))


def check_pcap(pcap: Path, *, fps: int = 15, tshark: str | None = None) -> dict:
    tshark = tshark or shutil.which("tshark")
    if not tshark:
        raise FileNotFoundError("tshark is not installed")
    if fps <= 0 or 90000 % fps:
        raise ValueError("fps must be a positive divisor of 90000")
    decode = ["udp.port==5004,rtp", "udp.port==5005,rtcp"]
    rtp_rows = _fields(tshark, pcap, decode, "rtp", [
        "rtp.seq", "rtp.timestamp", "rtp.marker", "rtp.ssrc"])
    rtcp_rows = _fields(tshark, pcap, decode, "rtcp", ["rtcp.pt"])
    malformed = _fields(tshark, pcap, decode, "_ws.malformed", ["frame.number"])
    packets = []
    for row in rtp_rows:
        if len(row) != 4 or not all(row):
            continue
        # tshark 4.x prints boolean fields (rtp.marker) as True/False.
        packets.append(tuple(_field(value) for value in row))
    issues: list[str] = []
    if not packets:
        issues.append("no RTP packets decoded")
    for previous, current in zip(packets, packets[1:]):
        if current[0] != ((previous[0] + 1) & 0xFFFF):
            issues.append(f"sequence discontinuity {previous[0]} -> {current[0]}")
            break
    timestamps = list(dict.fromkeys(packet[1] for packet in packets))
    expected_step = 90000 // fps
    for previous, current in zip(timestamps, timestamps[1:]):
        if ((current - previous) & 0xFFFFFFFF) != expected_step:
            issues.append(f"timestamp step {previous} -> {current} is not {expected_step}")
            break
    groups: dict[int, list[tuple[int, int, int, int]]] = {}
    for packet in packets:
        groups.setdefault(packet[1], []).append(packet)
    for timestamp, group in groups.items():
        marker_indexes = [index for index, packet in enumerate(group) if packet[2] == 1]
        if marker_indexes != [len(group) - 1]:
            issues.append(f"timestamp {timestamp}: marker must be set only on final packet")
            break
    ssrcs = sorted(set(packet[3] for packet in packets))
    if len(ssrcs) != 1:
        issues.append(f"expected one SSRC, found {len(ssrcs)}")
    if not rtcp_rows:
        issues.append("no RTCP packets decoded")
    if malformed:
        issues.append(f"{len(malformed)} malformed packet(s) in capture")
    return {"pcap": str(pcap), "rtp_packets": len(packets), "frames": len(groups),
            "rtcp_packets": len(rtcp_rows), "ssrcs": ssrcs,
            "expected_timestamp_step": expected_step, "malformed_packets": len(malformed),
            "checks": {"sequence_contiguous": not any("sequence" in x for x in issues),
                       "timestamp_step": not any("timestamp step" in x for x in issues),
                       "marker_last_only": not any("marker" in x for x in issues),
                       "constant_ssrc": len(ssrcs) == 1, "rtcp_decoded": bool(rtcp_rows),
                       "no_malformed": not malformed},
            "passed": not issues, "issues": issues}


def _field(value: str) -> int:
    lowered = value.strip().lower()
    if lowered in ("true", "false"):
        return int(lowered == "true")
    return int(value, 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pcap", type=Path)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--output", type=Path, help="write JSON report here")
    parser.add_argument("--tshark", help="path to tshark executable")
    args = parser.parse_args(argv)
    try:
        report = check_pcap(args.pcap, fps=args.fps, tshark=args.tshark)
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"tshark_check: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
