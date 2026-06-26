#!/usr/bin/env python3
"""Enable the Words of Power screen reader mod without using the visual Mods menu.

Why this exists:
    Rift Wizard 2's Steam Workshop update made mods opt-in -- a mod only loads if
    its name is in options2.dat -> 'enabled_mods'. That list is normally edited
    through the in-game Mods menu, which a blind player cannot read until the
    screen reader is already loaded. This tool breaks that catch-22 by adding
    'screen_reader' to enabled_mods directly.

Usage:
    Close Rift Wizard 2 first (the game re-saves options on exit and would
    overwrite this change). Then run the tool. Built as a standalone .exe it needs
    nothing installed; as a script run:  python enable_screen_reader.py
    Pass --disable to turn the mod back off.

Safety:
    options2.dat is a plain pickle of builtin types only. This tool reads the
    existing settings, appends one string, and writes them back -- keybinds,
    volumes, and other options are preserved.
"""

import argparse
import os
import pickle
import sys

MOD_NAME = "screen_reader"
OPTIONS_FILENAME = "options2.dat"
# Protocol 4 is readable by the game's bundled Python 3.8 (and everything newer).
PICKLE_PROTOCOL = 4


def _search_roots():
    """Directories to start the upward search from.

    When frozen by PyInstaller, __file__ points into a temp extraction dir, so we
    must use the real .exe location (sys.executable) instead.
    """
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    else:
        try:
            roots.append(os.path.dirname(os.path.abspath(__file__)))
        except NameError:
            pass
    roots.append(os.getcwd())
    return roots


def find_options_file():
    """Walk upward from each search root to find options2.dat."""
    for start in _search_roots():
        cur = start
        while True:
            candidate = os.path.join(cur, OPTIONS_FILENAME)
            if os.path.isfile(candidate):
                return candidate
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    return None


def _pause():
    """Keep the console open after a double-click so the result can be read/heard."""
    try:
        input("\nPress Enter to close...")
    except (EOFError, KeyboardInterrupt):
        pass


def run(disable, options_path):
    path = options_path or find_options_file()
    if not path or not os.path.isfile(path):
        print("ERROR: Could not find options2.dat.")
        print("Place this tool inside your Rift Wizard 2 install (e.g. in the mod")
        print("folder), or pass --options <path to options2.dat>.")
        return 1

    try:
        with open(path, "rb") as f:
            options = pickle.load(f)
    except Exception as exc:
        print("ERROR: Could not read %s: %s" % (path, exc))
        return 1

    if not isinstance(options, dict):
        print("ERROR: Unexpected options format in %s." % path)
        return 1

    enabled = options.get("enabled_mods")
    if not isinstance(enabled, list):
        enabled = []

    if disable:
        if MOD_NAME in enabled:
            enabled = [m for m in enabled if m != MOD_NAME]
            options["enabled_mods"] = enabled
            with open(path, "wb") as f:
                pickle.dump(options, f, protocol=PICKLE_PROTOCOL)
            print("Done. The screen reader mod is now DISABLED.")
        else:
            print("The screen reader mod was already disabled. No change made.")
        print("Enabled mods: %s" % (enabled or "(none)"))
        return 0

    if MOD_NAME in enabled:
        print("The screen reader mod is already enabled. No change needed.")
        print("Enabled mods: %s" % enabled)
        return 0

    enabled.append(MOD_NAME)
    options["enabled_mods"] = enabled
    with open(path, "wb") as f:
        pickle.dump(options, f, protocol=PICKLE_PROTOCOL)

    print("Done. The screen reader mod is now ENABLED.")
    print("Updated: %s" % path)
    print("Enabled mods: %s" % enabled)
    print("Make sure Rift Wizard 2 is fully closed, then start it --")
    print("the screen reader will speak on launch.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Enable or disable the Words of Power screen reader mod for Rift Wizard 2."
    )
    parser.add_argument(
        "--disable", action="store_true",
        help="Remove the mod from enabled_mods instead of adding it.",
    )
    parser.add_argument(
        "--options", help="Explicit path to options2.dat (otherwise auto-detected).",
    )
    parser.add_argument(
        "--no-pause", action="store_true",
        help="Do not wait for Enter before exiting (for use inside other scripts).",
    )
    args = parser.parse_args()

    code = run(args.disable, args.options)
    if not args.no_pause:
        _pause()
    return code


if __name__ == "__main__":
    sys.exit(main())
