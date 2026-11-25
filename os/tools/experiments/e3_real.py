#!/usr/bin/env python3
"""Shuffled E3 campaign on the Pi UART (default /dev/ttyAMA0); run only on the Pi."""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import random
import shlex
import shutil
import signal
import subprocess
import sys

import e_campaign as campaign
sys.path.insert(0, str(campaign.ROOT / 'analysis'))
import e3_real_summary as summary


LOADS = ('B0_idle', 'B2_memrate_c23')
POLICIES = (('fifo', 'fifo'), ('fifo', 'latest'), ('latest', 'latest'))


def cell_name(load, ip, bp):
    return f'{load}/{ip}-{bp}'


def all_cells():
    return [cell_name(load, ip, bp) for load in LOADS for ip, bp in POLICIES]


def plan(reps, cells=None):
    """Shuffled run order. ``cells`` filters by load (``B2_memrate_c23``),
    policy pair (``fifo-latest``) or full cell (``B2_memrate_c23/fifo-latest``)."""
    runs = [('P1', load, ip, bp, rep) for rep in range(1, reps + 1)
            for load in LOADS for ip, bp in POLICIES]
    if cells:
        wanted = set(cells)
        unknown = wanted - set(LOADS) - {f'{ip}-{bp}' for ip, bp in POLICIES} - set(all_cells())
        if unknown:
            raise ValueError(f'unknown --cells value(s): {sorted(unknown)}; choose from {all_cells()}')
        runs = [r for r in runs if r[1] in wanted or f'{r[2]}-{r[3]}' in wanted
                or cell_name(r[1], r[2], r[3]) in wanted]
    random.Random(42).shuffle(runs)
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('reps', type=campaign.positive, nargs='?', default=3)
    parser.add_argument('seconds', type=campaign.positive, nargs='?', default=60)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--rearm-command', default=f"bash {shlex.quote(str(campaign.ROOT / 'scripts/stm32/reset.sh'))}",
                        help='synchronous MCU reset argv; after model initialization, before UART launch, timeout 15 s')
    parser.add_argument('--fresh-timeout', type=campaign.positive, default=30)
    parser.add_argument('--cells', type=lambda s: [c for c in s.split(',') if c],
                        help='comma list of loads, policy pairs or LOAD/IN-BRIDGE cells; '
                             'e.g. B2_memrate_c23 = 3 cells. Default: all 6 cells')
    parser.add_argument('--serial', default='/dev/ttyAMA0', help='Pi UART device (default /dev/ttyAMA0)')
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.model = args.model.resolve()
    args.python = shutil.which(os.environ.get('PYTHON', 'python3'))
    args.stage = 'onnx'
    args.summary_func = summary.summarize_run
    print('Run command: ' + shlex.join(['env', f'PYTHON={os.environ.get("PYTHON", "python3")}',
          'bash', str(campaign.ROOT / 'tools/experiments/e3_real.sh')] + sys.argv[1:]), flush=True)
    try:
        n = len(plan(args.reps, args.cells))
    except ValueError as exc:
        print(f'e3_real: {exc}', file=sys.stderr)
        return 2
    print(f'Planned runs: {n}', flush=True)
    print(f'Wall-time estimate: {n * args.seconds / 60:.1f} min measured; '
          f'allow {n * (args.seconds + 30) / 60:.1f} min plus initial build/model startup.', flush=True)
    try:
        if platform.system() != 'Linux':
            raise ValueError('Run on the Linux Pi target, not macOS')
        if args.out.exists():
            raise ValueError(f'Refusing existing campaign: {args.out}')
        if not args.model.is_file() or not args.python:
            raise ValueError('existing --model and PYTHON interpreter required')
        command = shlex.split(args.rearm_command)
        if not command:
            raise ValueError('empty rearm command')
        for tool in ('make', 'python3', 'taskset', 'stress-ng', 'vcgencmd', 'git', 'lscpu', 'sudo', command[0]):
            if shutil.which(tool) is None:
                raise ValueError(f'Missing dependency: {tool}')
        subprocess.run(['sudo', '-n', 'true'], check=True)
        subprocess.run([args.python, '-c', 'import numpy, onnxruntime'], check=True)
        subprocess.run(['make', '-C', str(campaign.ROOT / 'linux'), 'all'], check=True)
        args.out.mkdir(parents=True)
        if not Path(args.serial).exists():
            raise ValueError(f'serial device not found: {args.serial}')
        order = plan(args.reps, args.cells)
        campaign.json_write(args.out / 'campaign.json', dict(experiment='E3_REAL', reps=args.reps,
            seconds=args.seconds, seed=42, stage='onnx', model=str(args.model), python=args.python,
            model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
            rearm_command=args.rearm_command, serial=args.serial, baud=921600, cells=args.cells or all_cells(),
            rms_bound_us=200, monitor_period_seconds=.5, evidence=summary.EVIDENCE,
            source_cpu=1, source_priority=60, bridge_cpu=1, bridge_priority=70,
            inference_cpu=0, inference_policy='SCHED_OTHER', threads=1))
        campaign.json_write(args.out / 'order.json', order)
        (args.out / 'platform.txt').write_text(campaign.capture(['stress-ng', '--version']) + '\n' +
                                             campaign.capture(['lscpu']) + '\n')
        for condition in order:
            print(f'Running {condition}', flush=True)
            campaign.execute_run(args, 'E3_REAL', condition)
        runs, _ = summary.write_summary(args.out)
        (args.out / 'DONE').touch()
        print(f"Complete: {sum(r['valid'] for r in runs)}/{len(runs)} valid; {args.out / 'summary'}")
        return 0 if all(r['valid'] for r in runs) else 1
    except (ValueError, OSError, subprocess.SubprocessError, InterruptedError) as exc:
        if args.out.is_dir() and list(args.out.glob('E3_REAL*/condition.json')):
            summary.write_summary(args.out)
        print(f'e3_real: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    def interrupted(signum, frame):
        raise InterruptedError(f'interrupted by signal {signum}')
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    sys.exit(main())
