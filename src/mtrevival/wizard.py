"""The no-arguments path: a guided fix for someone who double-clicked the exe.

Everything here is a thin conversation over ``fixpack``. The wizard makes the
same decisions the CLI makes, but asks instead of expecting flags, and does
the one step the CLI only prints — granting write access to the game folder
— by running ``icacls`` elevated itself, so the player sees a Windows prompt
rather than a command to type.

``run`` takes its input and output functions as parameters so tests can
script a whole session without a console.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Callable

from . import d3denum, fixpack, gameconfig, music

Ask = Callable[[str], str]
Say = Callable[[str], None]

BANNER = """\
Monopoly Tycoon fix
===================
Makes the 2001 game run on Windows 10 and 11: picks a display adapter the
game can start on, sets the resolution, and restores the music. It writes
one text file (config.cfg) in the game folder and, for music, registers one
small file for your user account. Nothing in the game itself is changed.
"""

VERIFIED_WIDE = (1920, 1080)


def run(ask: Ask = input, say: Say = print, game_dir: Path | None = None) -> int:
    """The whole conversation. Returns a process exit code."""
    say(BANNER)

    try:
        game_dir = fixpack.find_install(game_dir)
    except fixpack.FixError:
        game_dir = ask_for_install(ask, say)
        if game_dir is None:
            return 2
    say("Game folder: %s" % game_dir)
    say("Game version: %s" % fixpack.game_version(game_dir))

    if not fixpack.is_writable(game_dir):
        say("")
        say("Windows does not let the game save into its own folder, which is why")
        say("its settings never stick. Fixing that needs one permission change;")
        say("Windows will ask you to allow it.")
        if not grant_access(game_dir):
            say("")
            say("The permission change did not go through. Run this once in an")
            say("elevated PowerShell, then try again:")
            say("    " + fixpack.grant_command(game_dir))
            return 1
        say("Done: the game can now save into its folder.")

    adapters, source = fixpack.read_adapters(game_dir)
    choices = resolution_choices(adapters, current_desktop_mode())
    if not choices:
        say("")
        say("No display adapter offers a mode the game can use (640x480 or")
        say("1920x1080). A rotated display can cause this; rotate it to")
        say("landscape or attach a landscape display, then run this again.")
        return 1
    width, height = choose(ask, say, "Resolution", choices)

    with_music = False
    if music.reader_available():
        with_music = yes_no(ask, "Restore the music?", default=True)
    else:
        say("")
        say("Windows Media is not installed (Windows N edition?), so the music")
        say("stays off. Install the Media Feature Pack and run this again to get it.")

    plan = fixpack.build_plan(game_dir, width, height, False, with_music)
    say("")
    say(fixpack.describe(plan))
    if not plan.ok:
        return 1
    say("")
    if not yes_no(ask, "Apply this?", default=True):
        say("Nothing changed.")
        return 0
    try:
        backup = fixpack.apply(plan)
    except fixpack.FixError as error:
        say("")
        say("Could not apply the fix: %s" % error)
        return 1
    say("")
    say("Done. Wrote %s" % plan.config_path)
    if backup:
        say("Your previous config.cfg is kept as %s" % backup.name)
    if plan.music:
        say("Music is on. Do not run the game 'as administrator', or it will not")
        say("find the music component.")
    say("Launch the game with mc.exe in %s" % game_dir)
    return 0


def ask_for_install(ask: Ask, say: Say) -> Path | None:
    """Ask until a folder with mc.exe is given, or the answer is blank."""
    say("")
    say("Could not find the game. Install it from your CD first.")
    say("If it is installed somewhere unusual, type the folder that contains")
    say("mc.exe (or leave empty to quit).")
    while True:
        answer = ask("Game folder: ").strip().strip('"')
        if not answer:
            return None
        try:
            return fixpack.find_install(Path(answer))
        except fixpack.FixError as error:
            say(str(error))


def resolution_choices(adapters: list[d3denum.Adapter],
                       desktop: tuple[int, int] | None) -> list[tuple[str, tuple[int, int]]]:
    """Resolutions worth offering, verified ones first.

    1920x1080 fullscreen was verified with a correctly laid-out UI, so it is
    the default when an adapter lists it. The desktop mode is offered as
    unverified. 640x480 is the original and always works when any adapter
    offers it (a portrait-only setup offers none).
    """
    out: list[tuple[str, tuple[int, int]]] = []

    def offered(mode: tuple[int, int]) -> bool:
        # Landscape only: the game's UI is landscape, and a portrait primary
        # display lists its own rotated mode, which is the crash we avoid.
        return mode[0] > mode[1] and d3denum.choose_adapter(adapters, mode[0], mode[1]) is not None

    if offered(VERIFIED_WIDE):
        out.append(("%dx%d fullscreen (recommended)" % VERIFIED_WIDE, VERIFIED_WIDE))
    if desktop and desktop != VERIFIED_WIDE and desktop != (640, 480) and offered(desktop):
        out.append(("%dx%d fullscreen (your desktop; not verified, try it)" % desktop, desktop))
    original = (gameconfig.DEFAULT_WIDTH, gameconfig.DEFAULT_HEIGHT)
    if offered(original):
        out.append(("%dx%d fullscreen (the original)" % original, original))
    return out


def choose(ask: Ask, say: Say, title: str, choices):
    """Numbered menu; blank or nonsense picks the first entry."""
    say("")
    say("%s:" % title)
    for number, (label, _) in enumerate(choices, 1):
        say("  [%d] %s" % (number, label))
    while True:
        answer = ask("Choose 1-%d [1]: " % len(choices)).strip()
        if answer == "":
            return choices[0][1]
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1][1]
        say("Type a number from 1 to %d." % len(choices))


def yes_no(ask: Ask, question: str, default: bool) -> bool:
    answer = ask("%s [%s]: " % (question, "Y/n" if default else "y/N")).strip().lower()
    if answer == "":
        return default
    return answer[0] == "y"


def current_desktop_mode() -> tuple[int, int] | None:
    """The primary display's current resolution, or None off Windows."""
    try:
        from . import displays
        return displays.current_desktop_mode()
    except (ImportError, AttributeError, OSError):
        return None


def grant_access(game_dir: Path) -> bool:
    """Run icacls elevated to give this account write access, then re-check."""
    user = os.environ.get("USERNAME") or os.getlogin()
    args = '"%s" /grant "%s:(OI)(CI)M" /T' % (game_dir, user)
    if not run_elevated("icacls", args):
        return False
    return fixpack.is_writable(game_dir)


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("fMask", ctypes.c_ulong),
        ("hwnd", ctypes.c_void_p),
        ("lpVerb", ctypes.c_wchar_p),
        ("lpFile", ctypes.c_wchar_p),
        ("lpParameters", ctypes.c_wchar_p),
        ("lpDirectory", ctypes.c_wchar_p),
        ("nShow", ctypes.c_int),
        ("hInstApp", ctypes.c_void_p),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", ctypes.c_wchar_p),
        ("hkeyClass", ctypes.c_void_p),
        ("dwHotKey", ctypes.c_ulong),
        ("hIcon", ctypes.c_void_p),
        ("hProcess", ctypes.c_void_p),
    ]


def run_elevated(program: str, args: str) -> bool:
    """ShellExecuteEx with the 'runas' verb; waits; True on exit code 0.

    Returns False if the UAC prompt was declined or the program failed.
    """
    if not hasattr(ctypes, "windll"):
        return False
    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SW_HIDE = 0
    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = program
    info.lpParameters = args
    info.nShow = SW_HIDE
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        return False
    if not info.hProcess:
        return False
    kernel32 = ctypes.windll.kernel32
    kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
    code = ctypes.c_ulong()
    kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    kernel32.CloseHandle(info.hProcess)
    return code.value == 0


def owns_console() -> bool:
    """True if this process was started by double-click (it is alone on its console)."""
    if not hasattr(ctypes, "windll"):
        return False
    pids = (ctypes.c_ulong * 2)()
    count = ctypes.windll.kernel32.GetConsoleProcessList(pids, 2)
    return count == 1


def main_interactive() -> int:
    """Entry for a double-click: run, then wait so the window does not vanish."""
    code = run()
    if owns_console():
        try:
            input("\nPress Enter to close this window.")
        except EOFError:
            pass
    return code


if __name__ == "__main__":
    sys.exit(main_interactive())
