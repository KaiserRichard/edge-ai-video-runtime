"""Unified command entry point used by RTP scenario templates."""

import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m rtp")
    parser.add_argument("role", choices=("sender", "receiver"))
    args, remaining = parser.parse_known_args(argv)
    if args.role == "sender":
        from .sender import main as run
    else:
        from .receiver import main as run
    return run(remaining)


if __name__ == "__main__":
    raise SystemExit(main())
