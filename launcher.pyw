"""
Claude Monitor launcher (written for Windows, works on any OS).

    pythonw launcher.pyw            start the server if needed, open the dashboard
    python  launcher.pyw --stop     stop the background server started by this launcher

The Windows shortcut created by install.bat runs this file with pythonw.exe, so
no console window appears. It is plain standard library and keeps every path as
a Python str, so install folders / user names with non-ASCII characters
(e.g. Persian) work -- which generated .bat/.vbs launchers could not guarantee.
"""

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import webbrowser

HOST = "127.0.0.1"
# Keep in sync with server/server.py, extension/manifest.json, extension/background.js
PORT = 8765
URL = "http://localhost:%d/" % PORT

ROOT = os.path.dirname(os.path.abspath(__file__))
SERVER_PY = os.path.join(ROOT, "server", "server.py")
LOG_PATH = os.path.join(tempfile.gettempdir(), "claude-monitor.log")
PID_PATH = os.path.join(tempfile.gettempdir(), "claude-monitor.pid")

IS_WINDOWS = os.name == "nt"
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def notify(text, error=False):
    """Tell the user something. pythonw.exe has no console, so use a message box there."""
    if IS_WINDOWS and sys.stdout is None:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, "Claude Monitor", 0x10 if error else 0x40)
            return
        except Exception:
            pass
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        stream.write(text + "\n")


def server_is_up(timeout=0.5):
    try:
        with socket.create_connection((HOST, PORT), timeout=timeout):
            return True
    except OSError:
        return False


def server_interpreter():
    """Use python.exe (not pythonw.exe) for the server so it gets valid stdout/stderr
    handles for the log file. It is started with CREATE_NO_WINDOW, so nothing is shown."""
    exe = sys.executable
    if IS_WINDOWS and os.path.basename(exe).lower() == "pythonw.exe":
        candidate = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(candidate):
            return candidate
    return exe


def start_server():
    env = dict(os.environ)
    # The server prints Persian text; redirected output would otherwise use the
    # Windows ANSI code page (e.g. cp1252) and crash on startup.
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    if IS_WINDOWS:
        extra = {"creationflags": CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP}
    else:
        extra = {"start_new_session": True}

    with open(LOG_PATH, "ab") as log:
        proc = subprocess.Popen(
            [server_interpreter(), "-u", SERVER_PY],
            cwd=os.path.dirname(SERVER_PY),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            env=env,
            close_fds=True,
            **extra
        )
    try:
        with open(PID_PATH, "w") as f:
            f.write(str(proc.pid))
    except OSError:
        pass
    return proc


def wait_until_up(proc, seconds=15.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if server_is_up():
            return True
        if proc.poll() is not None:  # the server exited -> it failed to start
            return server_is_up()
        time.sleep(0.25)
    return False


def _looks_like_our_server(pid):
    """Guard against a stale PID file pointing at an unrelated process that reused the PID."""
    if IS_WINDOWS:
        try:
            out = subprocess.run(
                ["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"],
                capture_output=True, text=True, errors="replace",
                creationflags=CREATE_NO_WINDOW,
            ).stdout.lower()
        except OSError:
            return False
        return "python" in out
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            return b"server.py" in f.read()
    except OSError:
        return False


def stop_server():
    try:
        with open(PID_PATH) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        notify("Claude Monitor: no running server found (no PID file).")
        return 1
    if not _looks_like_our_server(pid):
        notify("Claude Monitor: the server is not running (stale PID file removed).")
        _remove_pid_file()
        return 0
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, creationflags=CREATE_NO_WINDOW)
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError as e:
        notify("Claude Monitor: could not stop the server: %s" % e, error=True)
        return 1
    _remove_pid_file()
    notify("Claude Monitor: server stopped.")
    return 0


def _remove_pid_file():
    try:
        os.remove(PID_PATH)
    except OSError:
        pass


def main(argv):
    if "--stop" in argv:
        return stop_server()

    if not server_is_up():
        proc = start_server()
        if not wait_until_up(proc):
            notify("The Claude Monitor server did not start.\n\nSee the log for details:\n" + LOG_PATH, error=True)
            return 1
    webbrowser.open(URL)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
