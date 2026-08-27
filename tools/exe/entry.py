"""PyInstaller entry point for MonopolyTycoonFix.exe.

Double-click runs the wizard; arguments go to the normal CLI.
"""

import sys

from mtrevival.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
