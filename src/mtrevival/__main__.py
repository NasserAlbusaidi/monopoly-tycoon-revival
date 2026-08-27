"""Command line entry point: ``python -m mtrevival``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import fixpack


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mtrevival",
        description="Make Monopoly Tycoon (2001) run on modern Windows.")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("check", "report what would be done, change nothing"),
                            ("fix", "write config.cfg with a working adapter")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--game-dir", type=Path, default=None,
                       help="install directory containing mc.exe")

    p = sub.add_parser("adapters", help="list adapters and whether they fit")
    p.add_argument("--game-dir", type=Path, default=None)

    args = parser.parse_args(argv)

    try:
        game_dir = fixpack.find_install(args.game_dir)
    except fixpack.FixError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2

    if args.command == "adapters":
        adapters, source = fixpack.read_adapters(game_dir)
        print("source: %s" % source)
        for adapter in adapters:
            fits = adapter.supports(fixpack.TARGET_WIDTH, fixpack.TARGET_HEIGHT)
            print("  adapter %d  %-34s modes=%-4d %s%s"
                  % (adapter.index, adapter.description or "(unnamed)",
                     len(adapter.modes),
                     "OK 640x480" if fits else "no 640x480",
                     "  [portrait]" if adapter.is_portrait else ""))
        return 0

    plan = fixpack.build_plan(game_dir)
    print(fixpack.describe(plan))

    if args.command == "check":
        return 0 if plan.ok else 1

    try:
        backup = fixpack.apply(plan)
    except fixpack.FixError as error:
        print("\nerror: %s" % error, file=sys.stderr)
        return 1

    print("\nWrote %s" % plan.config_path)
    if backup:
        print("Backed up previous config to %s" % backup)
    print("Launch the game with mc.exe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
