#!/usr/bin/env python3
"""Run an RTP scenario from YAML, with a fully printable dry-run mode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment diagnostic
    raise SystemExit("PyYAML is required to read scenario YAML") from exc

from netem import netem_remove, netem_replace


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "rtp" / "results"


def _ssh(host: str | None, command: str) -> str:
    if not host or host in ("localhost", "local"):
        return command
    return "ssh " + shlex.quote(host) + " " + shlex.quote(command)


def _run(command: str, *, dry_run: bool) -> str:
    print("$ " + command, flush=True)
    if dry_run:
        return ""
    completed = subprocess.run(command, shell=True, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, check=True)
    return completed.stdout


def _capture(command: str, *, dry_run: bool) -> str:
    print("$ " + command, flush=True)
    if dry_run:
        return ""
    return subprocess.run(command, shell=True, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=True).stdout.strip()


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict) or not isinstance(config.get("scenario"), str):
        raise ValueError("config must be a mapping with a scenario name")
    for key in ("sender", "receiver", "ai"):
        if key not in config.get("commands", {}):
            raise ValueError(f"config is missing commands.{key}")
    if not isinstance(config.get("steps"), list) or not config["steps"]:
        raise ValueError("config must define at least one impairment step")
    if int(config.get("repetitions", 0)) < 1:
        raise ValueError("repetitions must be positive")
    return config


def _service_start(host: str | None, label: str, command: str, run_dir: str) -> str:
    remote_dir = shlex.quote(run_dir)
    return _ssh(host, f"mkdir -p {remote_dir}; nohup sh -lc {shlex.quote('exec ' + command)} "
                       f">{remote_dir}/{label}.log 2>&1 & echo $! > {remote_dir}/{label}.pid")


def _service_stop(host: str | None, label: str, run_dir: str) -> str:
    d = shlex.quote(run_dir)
    return _ssh(host, f"if test -f {d}/{label}.pid; then kill $(cat {d}/{label}.pid) "
                       f"2>/dev/null || true; fi")


def _metadata(host: str | None, run_dir: str, config: dict, repetition: int,
              seed: int | None, *, final: bool) -> str:
    script = r'''import json, pathlib, subprocess, sys
path=pathlib.Path(sys.argv[1]); final=sys.argv[2] == "1"
def output(args):
    try:
        return subprocess.run(args, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL).stdout.strip()
    except OSError:
        return ""
state={"git_hash": output(["git", "rev-parse", "HEAD"]),
       "kernel": output(["uname", "-r"]),
       "throttle": output(["vcgencmd", "get_throttled"]),
       "wifi_link": output(["iw", "dev", "wlan0", "link"])}
if not final:
    path.with_name("_meta_before.json").write_text(json.dumps(state), encoding="utf-8")
else:
    before=json.loads(path.with_name("_meta_before.json").read_text(encoding="utf-8"))
    static=json.loads(sys.argv[3])
    meta={**static, **{k: state[k] for k in ("git_hash", "kernel")},
          "throttle_before": before["throttle"], "throttle_after": state["throttle"],
          "iw_link_before": before["wifi_link"], "iw_link_after": state["wifi_link"]}
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
'''
    static = {"scenario": config["scenario"], "config": config.get("config", "default"),
              "netem_lines": [str(s.get("netem", "")) for s in config["steps"]],
              "repetition": repetition, "seed": seed}
    args = ["python3", "-c", script, run_dir + "/meta.json", "1" if final else "0"]
    if final:
        args.append(json.dumps(static, separators=(",", ":")))
    return _ssh(host, " ".join(shlex.quote(a) for a in args))


def _endpoint_command(template: str, role: str, values: dict, run_dir: str,
                      seed: int | None) -> str:
    """Translate NET1's historical module templates to the unified RTP CLI."""
    rendered = template.format(**values)
    tokens = shlex.split(rendered)
    if len(tokens) >= 4 and tokens[0] in ("python", "python3") and tokens[1:3] == ["-m", f"rtp.{role}"]:
        tokens = tokens[:1] + ["-m", "rtp", role] + tokens[3:]
    else:
        raise ValueError(f"unsupported {role} command template: {template}")
    # The old T2 sender accidentally carried a receiver-only playout option.
    # Receiver policy/interval sweeps are expressed by scenario variants; these
    # legacy multi-value options cannot be passed to one endpoint invocation.
    if role == "sender":
        while "--playout-ms" in tokens:
            i = tokens.index("--playout-ms")
            del tokens[i:i + 2]
    else:
        for option in ("--policy", "--rr-interval"):
            if option in tokens:
                i = tokens.index(option)
                del tokens[i:i + (3 if option == "--policy" else 2)]
    tokens.extend(("--out-dir", run_dir, "--rtcp-csv", f"{role}_rtcp.csv"))
    if role == "receiver":
        tokens.extend(("--duration", str(values["receiver_duration_s"]), "--ai", "off"))
    elif seed is not None:
        tokens.extend(("--seed", str(seed)))
    return "env PYTHONPATH=rtp${PYTHONPATH:+:$PYTHONPATH} " + " ".join(shlex.quote(t) for t in tokens)


def plan(config: dict, *, output: Path, repetitions: int | None = None) -> list[str]:
    count = repetitions or int(config["repetitions"])
    sender_host = config.get("links", {}).get("sender", "local")
    receiver_host = config.get("links", {}).get("receiver", "local")
    interface = config.get("interface", "eth0")
    commands: list[str] = []
    for rep in range(1, count + 1):
        run_dir = str(output / config["scenario"] / config.get("config", "default") / f"run{rep}")
        values = {"duration_s": sum(float(s["duration_s"]) for s in config["steps"]),
                  "run_dir": run_dir, "repetition": rep,
                  "receiver_duration_s": sum(float(s["duration_s"]) for s in config["steps"]) + 3,
                  "seed": config.get("seeds", [None] * count)[rep - 1]
                  if len(config.get("seeds", [])) >= rep else rep}
        commands.append(f"mkdir -p {shlex.quote(run_dir)}")
        commands.append(_ssh(sender_host, f"mkdir -p {shlex.quote(run_dir)}"))
        commands.append(_metadata(sender_host, run_dir, config, rep, values["seed"], final=False))
        # Record device/kernel state around every repetition; commands are executed on the
        # sender because netem and the Wi-Fi/throttle observations describe that host.
        commands.extend(_ssh(sender_host, c) for c in (
            "git rev-parse HEAD", "uname -r", "vcgencmd get_throttled 2>/dev/null || true",
            "iw dev wlan0 link 2>/dev/null || true"))
        commands.append(_service_start(receiver_host, "tcpdump",
            f"tcpdump -i {shlex.quote(config.get('capture_interface', 'any'))} -s 128 -U -w "
            f"{shlex.quote(run_dir + '/capture.pcap')}", run_dir))
        commands.append("sleep 1")
        commands.append(_service_start(receiver_host, "receiver",
            _endpoint_command(config["commands"]["receiver"], "receiver", values, run_dir, values["seed"]), run_dir))
        steps_script = ["set -e", "cleanup() { " + netem_remove(interface) + "; }",
                        "trap cleanup EXIT INT TERM", netem_remove(interface)]
        sender_command = _endpoint_command(config["commands"]["sender"], "sender", values, run_dir, values["seed"])
        steps_script.append(f"{sender_command} >{shlex.quote(run_dir + '/sender.log')} 2>&1 & sender_pid=$!")
        for step in config["steps"]:
            line = str(step.get("netem", "")).strip()
            if line:
                steps_script.append(netem_replace(interface, line))
            else:
                steps_script.append(netem_remove(interface))
            steps_script.append("sleep " + shlex.quote(str(float(step["duration_s"]))))
        steps_script.append("wait $sender_pid")
        commands.append(_ssh(sender_host, "sh -lc " + shlex.quote("; ".join(steps_script))))
        commands.extend((_service_stop(receiver_host, "tcpdump", run_dir),
                         _service_stop(receiver_host, "receiver", run_dir)))
        merge_code = "import csv,pathlib,sys; d=pathlib.Path(sys.argv[1]); rows=[]; header=None\n" \
            "for name in ('sender_rtcp.csv','receiver_rtcp.csv'):\n" \
            " p=d/name\n" \
            " if p.exists():\n" \
            "  with p.open(newline='') as f:\n" \
            "   r=csv.DictReader(f); header=header or r.fieldnames; rows.extend(r)\n" \
            "with (d/'rtcp.csv').open('w',newline='') as f:\n" \
            " w=csv.DictWriter(f,fieldnames=header); w.writeheader(); w.writerows(sorted(rows,key=lambda x:int(x['t_mono_ns'])))\n"
        merge_rtcp = "python3 -c " + shlex.quote(merge_code) + " " + shlex.quote(run_dir)
        commands.append(merge_rtcp)
        commands.append(_metadata(sender_host, run_dir, config, rep, values["seed"], final=True))
        if receiver_host not in ("local", "localhost", None):
            commands.append(f"scp {shlex.quote(receiver_host + ':' + run_dir + '/capture.pcap')} "
                            f"{shlex.quote(run_dir + '/capture.pcap')}")
    return commands


def execute(config: dict, commands: list[str], *, output: Path, dry_run: bool) -> None:
    if dry_run:
        print("# NET1 legacy templates python -m rtp.sender / python -m rtp.receiver / "
              "python -m rtp.ai are translated to python -m rtp sender / receiver; "
              "AI runs inside the receiver process.")
        for command in commands:
            _run(command, dry_run=True)
        return
    # A runner-level cleanup is kept in addition to the sender-side EXIT trap so that an
    # interrupted SSH/sender command cannot leave an impairment installed.
    sender_host = config.get("links", {}).get("sender", "local")
    interface = config.get("interface", "eth0")
    try:
        for command in commands:
            _run(command, dry_run=False)
    finally:
        _run(_ssh(sender_host, netem_remove(interface)), dry_run=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="scenario YAML file")
    parser.add_argument("--dry-run", action="store_true", help="print every command without running it")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repetitions", type=int, help="override repetitions in YAML")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        commands = plan(config, output=args.output_dir.resolve(), repetitions=args.repetitions)
        execute(config, commands, output=args.output_dir, dry_run=args.dry_run)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"run_scenario: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
