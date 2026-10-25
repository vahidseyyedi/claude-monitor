"""
Creates the "Claude Monitor" shortcuts on Windows (Desktop + Start Menu).
Normally run for you by install.bat.

The shortcuts run  pythonw.exe launcher.pyw  : the server starts hidden and the
dashboard opens in your default browser.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
LAUNCHER = os.path.join(ROOT, "launcher.pyw")
ICON = os.path.join(ROOT, "assets", "claude-monitor.ico")  # .lnk icons must be .ico, not .png

CSIDL_PROGRAMS = 0x02          # <user>\Start Menu\Programs
CSIDL_DESKTOPDIRECTORY = 0x10  # the user's real Desktop (follows OneDrive folder redirection)
CREATE_NO_WINDOW = 0x08000000

# Values travel through environment variables, not the command line, so paths with
# spaces, quotes or non-ASCII characters (e.g. a Persian user name) survive intact.
PS_SCRIPT = (
    "$ErrorActionPreference='Stop';"
    "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:CM_LNK);"
    "$s.TargetPath=$env:CM_TARGET;"
    "$s.Arguments=$env:CM_ARGS;"
    "$s.WorkingDirectory=$env:CM_WORKDIR;"
    "$s.IconLocation=$env:CM_ICON;"
    "$s.Description='Claude Monitor';"
    "$s.Save()"
)


def known_folder(csidl):
    import ctypes
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) != 0:
        return None
    return buf.value


def make_shortcut(lnk_path, target):
    env = dict(os.environ)
    env.update({
        "CM_LNK": lnk_path,
        "CM_TARGET": target,
        "CM_ARGS": '"%s"' % LAUNCHER,
        "CM_WORKDIR": ROOT,
        "CM_ICON": (ICON if os.path.exists(ICON) else target) + ",0",
    })
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", PS_SCRIPT],
        env=env, capture_output=True, text=True, errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        return (result.stderr or result.stdout or "unknown error").strip()
    return None


def main():
    if os.name != "nt":
        print("This script creates Windows shortcuts. On Linux run:  bash install.sh")
        return 1
    if not os.path.exists(LAUNCHER):
        print("ERROR: launcher.pyw not found next to install_windows.py")
        return 1

    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        print("Warning: pythonw.exe not found, falling back to python.exe (a console window may flash).")
        pythonw = sys.executable

    created = 0
    for name, csidl in (("Desktop", CSIDL_DESKTOPDIRECTORY), ("Start Menu", CSIDL_PROGRAMS)):
        folder = known_folder(csidl)
        if not folder or not os.path.isdir(folder):
            print("Skipped %s: folder not found." % name)
            continue
        lnk = os.path.join(folder, "Claude Monitor.lnk")
        error = make_shortcut(lnk, pythonw)
        if error:
            print("Could not create the %s shortcut: %s" % (name, error))
        else:
            print("Created %s shortcut: %s" % (name, lnk))
            created += 1

    if not created:
        print("No shortcut could be created. You can still start Claude Monitor by running:")
        print('    "%s" "%s"' % (pythonw, LAUNCHER))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
