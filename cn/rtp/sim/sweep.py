"""Run reproducible ns-3 RTP grids for CN-T3, T4, T5 and T8."""
from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def configurations(scenario: str):
    """Yield (label, simulator options) for the scenario's design grid."""
    if scenario == "CN-T3":
        for loss in (0.0, 0.01, 0.05, 0.10):
            yield f"random-loss-{loss:g}", {"lossP": loss}
        yield "gilbert-elliott-5pct-burst4", {"lossP": 0.05, "geBurst": 4}
    elif scenario == "CN-T4":
        for (dist, jitter), playout in itertools.product(
                (("uniform", 5), ("normal", 20)), (20, 50, 100, 200)):
            yield f"{dist}-jitter-{jitter}ms-playout-{playout}ms", {
                "delayMs": 20, "jitterMs": jitter, "playoutMs": playout,
                "jitterDist": dist, "playoutAnchor": "first",
            }
    elif scenario == "CN-T5":
        for size in (3000, 8000, 16000):
            yield f"frame-{size}B", {"frameBytes": size, "lossP": 0.02}
    elif scenario == "CN-T8":
        for mode, abr in (("fixed", False), ("abr", True)):
            yield mode, {"lossSteps": "0:0,20:0.05,40:0.15,60:0", "abr": abr}
    else:
        raise ValueError(f"unsupported scenario: {scenario}")


def build_commands(binary: Path, out_root: Path, scenario: str, seeds=range(1, 6)):
    """Return deterministic argv lists, one per config and RngRun seed."""
    commands = []
    for label, options in configurations(scenario):
        for seed in seeds:
            out = out_root / scenario / label / f"seed-{seed:02d}"
            args = [str(binary), "--link=csma", "--fps=30", "--frameBytes=12000",
                    f"--simTime={80 if scenario == 'CN-T8' else 60}", f"--seed={seed}",
                    f"--run={seed}", f"--outDir={out}"]
            args.extend(f"--{key}={str(value).lower() if isinstance(value, bool) else value}"
                        for key, value in options.items())
            commands.append(args)
    return commands


def analyze_run(run_dir: Path) -> dict:
    """Call AN1 directly; its directory has no runnable __main__ module."""
    path = ROOT / "rtp/analysis/metrics.py"
    spec = importlib.util.spec_from_file_location("sim_rtp_an1", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metrics = module.compute_run_metrics(run_dir)
    # Missing AI observations remain unknown; encode JSON null, never invented zeros.
    clean = {key: None if isinstance(value, float) and value != value else value
             for key, value in metrics.items()}
    (run_dir / "summary.json").write_text(json.dumps(clean, indent=2, allow_nan=False) + "\n")
    return clean


def run_command(command: list[str]) -> dict:
    """Run a simulator command, record provenance, then analyze its shared CSVs."""
    started = time.monotonic()
    subprocess.run(command, cwd=ROOT, check=True)
    out = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--outDir=")))
    if not out.is_absolute():
        out = ROOT / out
    meta_path = out / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta.update({
        "git_hash": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_dirty": bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
        "wall_time_s": time.monotonic() - started,
        "command": command,
        "exit_code": 0,
    })
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return analyze_run(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=("CN-T3", "CN-T4", "CN-T5", "CN-T8"), nargs="+")
    parser.add_argument("--binary", type=Path, default=ROOT / "build/rtp-video")
    parser.add_argument("--out", type=Path, default=ROOT / "results/sim_rtp")
    args = parser.parse_args()
    if not args.binary.exists():
        subprocess.run([str(ROOT / "scripts/build_sim_rtp.sh"), str(args.binary)], check=True)
    for scenario in args.scenario:
        for command in build_commands(args.binary, args.out, scenario):
            run_command(command)
            if scenario == "CN-T8":
                try:
                    from .t8_steps import write_step_metrics
                except ImportError:
                    from t8_steps import write_step_metrics
                out = next(arg.split("=", 1)[1] for arg in command
                           if arg.startswith("--outDir="))
                write_step_metrics(Path(out))


if __name__ == "__main__":
    main()
