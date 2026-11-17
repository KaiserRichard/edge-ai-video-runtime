"""Scenario-level RTP plots from the shared run directory layout."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

try:  # Package import from an installed/namespace layout.
    from .metrics import analyze_config
except ImportError:  # Direct analysis/ on sys.path (the repository's current layout).
    from metrics import analyze_config


# One primary figure per scenario, chosen from the metrics in TEST_SCENARIOS.md.
_SCENARIO_METRICS = {
    "T2": ("capture_ai_latency_p95_ms", "Capture to AI result P95 (ms)"),
    "T3": ("packet_loss", "Packet loss ratio"),
    "T4": ("jitter_ms", "RFC 3550 jitter (ms)"),
    "T5": ("goodput_bps", "Goodput (bit/s)"),
    "T6": ("capture_ai_latency_p95_ms", "Capture to AI result P95 (ms)"),
    "T7": ("ai_result_avg_age_s", "AI-result time-average age (s)"),
    "T8": ("on_time_ratio", "On-time frame ratio"),
}


def plot_scenario(scenario_dir: str | Path, output_dir: str | Path | None = None) -> list[Path]:
    """Write one PNG and PDF per scenario directory, grouped by configuration.

    Config directories are the immediate children of ``scenario_dir`` and each
    contains ``run*`` directories. The y value is the run mean; error bars show
    the 95% Student-t confidence interval (min/max is reported separately by
    :func:`analysis.metrics.analyze_config`).
    """
    scenario_dir = Path(scenario_dir)
    output_dir = Path(output_dir) if output_dir else scenario_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    scenario = scenario_dir.name.upper().replace("CN-", "")
    metric, ylabel = _SCENARIO_METRICS.get(scenario, ("frame_loss", "Frame loss ratio"))
    configs = []
    for config in sorted(p for p in scenario_dir.iterdir() if p.is_dir()):
        runs, aggregate = analyze_config(config)
        if not runs:
            continue
        stats = aggregate[metric]
        if np.isfinite(stats["mean"]):
            configs.append((config.name, stats))
    if not configs:
        raise ValueError(f"no finite {metric} values found under {scenario_dir}")
    values = np.asarray([item[1]["mean"] for item in configs])
    low = np.asarray([item[1]["ci_low"] for item in configs])
    high = np.asarray([item[1]["ci_high"] for item in configs])
    errors = np.vstack((np.maximum(0, values - low), np.maximum(0, high - values)))
    fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    ax.errorbar(np.arange(len(configs)), values, yerr=errors, fmt="o-", capsize=4,
                color="#1F3A5F", ecolor="#2A9D8F")
    ax.set_xticks(np.arange(len(configs)), [item[0] for item in configs], rotation=25, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(f"CN-{scenario}: {ylabel}")
    ax.grid(True, axis="y", alpha=0.25)
    paths = []
    for suffix in ("png", "pdf"):
        path = output_dir / f"CN-{scenario}.{suffix}"
        fig.savefig(path, dpi=160 if suffix == "png" else None)
        paths.append(path)
    plt.close(fig)
    return paths


def plot_all(results_dir: str | Path, output_dir: str | Path | None = None) -> list[Path]:
    """Render available scenario directories (T2 through T8)."""
    results_dir = Path(results_dir)
    output_dir = Path(output_dir) if output_dir else results_dir
    paths = []
    for scenario in sorted(results_dir.iterdir()):
        if scenario.is_dir() and scenario.name.upper().replace("CN-", "") in _SCENARIO_METRICS:
            paths.extend(plot_scenario(scenario, output_dir / scenario.name))
    return paths
