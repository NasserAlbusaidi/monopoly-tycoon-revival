"""Command line entry point: ``python -m mtrevival``."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import fixpack

_RESOLUTION = re.compile(r"^(\d{3,4})x(\d{3,4})$")


def resolution(text: str) -> tuple[int, int]:
    """argparse type for WIDTHxHEIGHT."""
    m = _RESOLUTION.match(text.strip().lower())
    if not m:
        raise argparse.ArgumentTypeError(
            "expected WIDTHxHEIGHT such as 1920x1080, got %r" % text)
    return int(m.group(1)), int(m.group(2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mtrevival",
        description="Make Monopoly Tycoon (2001) run on modern Windows.")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--game-dir", type=Path, default=None,
                       help="install directory containing mc.exe")
        p.add_argument("--resolution", type=resolution,
                       default=(fixpack.DEFAULT_WIDTH, fixpack.DEFAULT_HEIGHT),
                       metavar="WxH",
                       help="display mode, default %dx%d; the adapter must list it"
                            % (fixpack.DEFAULT_WIDTH, fixpack.DEFAULT_HEIGHT))

    for name, help_text in (("check", "report what would be done, change nothing"),
                            ("fix", "write config.cfg with a working adapter")):
        p = sub.add_parser(name, help=help_text)
        common(p)
        p.add_argument("--windowed", action="store_true",
                       help="run in a window instead of fullscreen (needs patch 1.2)")
    common(sub.add_parser("adapters", help="list adapters and whether they fit"))

    args = parser.parse_args(argv)
    width, height = args.resolution
    windowed = getattr(args, "windowed", False)

    try:
        game_dir = fixpack.find_install(args.game_dir)
    except fixpack.FixError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2

    if args.command == "adapters":
        adapters, source = fixpack.read_adapters(game_dir)
        print("source: %s" % source)
        for adapter in adapters:
            fits = adapter.supports(width, height)
            print("  adapter %d  %-34s modes=%-4d %s%s"
                  % (adapter.index, adapter.description or "(unnamed)",
                     len(adapter.modes),
                     ("OK %dx%d" if fits else "no %dx%d") % (width, height),
                     "  [portrait]" if adapter.is_portrait else ""))
        return 0

    plan = fixpack.build_plan(game_dir, width, height, windowed)
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
