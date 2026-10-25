![](./assets/claude_monitor_banner.jpg)

EN | [FA](./README.md) 

# Claude Monitor

A local dashboard for tracking usage of multiple free-tier Claude (claude.ai) accounts in one place. The project has two parts:

1. **Browser extension (Chrome/Chromium/Edge)** — runs inside your open `claude.ai` tabs, reads the 5-hour session and weekly usage percentages, and reports them to a local server.
2. **Local Python server** — runs on your own machine (`http://localhost:8765`), stores the data reported by the extension for every account, and serves a web dashboard.

No data ever leaves your machine — everything is fully local.

---

## Features

- Shows each account's **5-hour session usage** and **weekly usage** percentage, plus the reset time.
- **Multi-account support** with custom labels you choose per account (e.g. `acc1`, `acc2`).
- Lists each account's chats with an approximate token-usage estimate per chat.
- Reads directly from claude.ai's own internal API using your existing browser session cookies — no separate login, password, or API token needed.
- Listens to the message SSE stream to capture the most accurate, real-time usage numbers.
- A simple web dashboard with one card per account, color-coded (green/yellow/red) by usage level.
- One-click server launch (a desktop icon on Linux, Desktop and Start Menu shortcuts on Windows) — no need to open a terminal every time.
- Reset times are shown in **your computer's local time zone** and match the countdown next to them.
- **Local and locked down**: the server listens on `localhost` only and answers only the dashboard and the extension, so other websites open in your browser cannot read your chat history.
- **Safe storage**: data is saved atomically, and an incomplete report (e.g. a failed chat fetch, or a tab that has not seen the usage stream yet) never wipes previously stored chats or usage numbers.

---

## Requirements

- A Chromium-based browser: **Google Chrome**, **Microsoft Edge**, **Brave**, or similar.
- **Python 3** installed on your machine (3.8+ is enough).
- At least one claude.ai account you're logged into in the browser.

---

![](./assets/Screenshot_01.png)

![](./assets/Screenshot_02.png)

## Installation — Step by Step

### Step 1: Install the browser extension

Since this extension isn't published on the Chrome Web Store, you install it manually as an "unpacked" extension:

1. Unzip the project folder (`claude-monitor`) if you received it as a zip.
2. Open Chrome or Edge and go to:
   - Chrome: `chrome://extensions`
   - Edge: `edge://extensions`
3. Turn on **Developer mode** (toggle usually in the top-right corner).
4. Click **Load unpacked**.
5. In the folder picker, select the `extension` folder inside the project (not the whole project — just the `extension` subfolder).
6. The extension **Claude Multi-Account Monitor** will appear in your extensions list. Pin its icon to the toolbar so it's always accessible.

> Note: if you later move or delete the extension's folder, you'll need to repeat step 4, since the browser remembers the folder's path.

#### Setting an account label

For each account you're logged into `claude.ai` with (e.g. across different Chrome profiles or multiple Incognito windows):

1. Click the extension's icon in the toolbar.
2. Type a name for this account (e.g. `acc1`, `work`, `personal`).
3. Click **Save**.

This label is only used to tell accounts apart on your dashboard and is never sent anywhere except your own local server.

> Note: for security the server sanitizes labels: quotes (`"` and `'`), backticks, `<`, `>`, `&`, backslashes and control characters are removed, `::` becomes `:`, and the label is cut to 60 characters. Prefer simple names (e.g. `acc1`, `work`). If nothing is left after cleaning, the label becomes "unnamed".

### Step 2: Set up the local server

#### Option A) Linux

1. Open a terminal in the project folder.
2. Run the install script once:
   ```bash
   bash install.sh
   ```
3. This creates a **Claude Monitor** icon on your desktop and in the applications menu.
4. From now on, just click that icon — the server starts automatically in the background (no terminal window) and your default browser opens the dashboard.
5. Server logs are written to `/tmp/claude-monitor.log`.
6. To stop the server: `pkill -f "python3 server.py"`

#### Option B) Windows

1. Double-click `install.bat` (it lives in the project's root folder, next to the `server` folder). Administrator rights are not needed.
2. It finds your Python 3 and creates a **Claude Monitor** shortcut on your Desktop and in the Start Menu.
3. From now on, double-clicking that shortcut starts the server hidden in the background (no console window) and opens the dashboard in your default browser.
4. Server logs are written to `%TEMP%\claude-monitor.log`.
5. To stop the background server, run this in the project folder (CMD or PowerShell):
   ```bat
   py -3 launcher.pyw --stop
   ```
   (or `python launcher.pyw --stop` if you have no `py`). As a last resort, end the server's `python.exe` in Task Manager.

> **Note:** the shortcut stores the project folder and the Python path as absolute paths. If you move or rename the project folder, or replace/uninstall Python, run `install.bat` again to recreate the shortcut.

**What the Windows files do** (all three are needed — none is redundant):

| File | Purpose |
|---|---|
| `install.bat` | Double-clicked once; finds a real Python and runs `install_windows.py` |
| `install_windows.py` | Creates the Desktop and Start Menu shortcuts (with a `.ico` icon); finds the real Desktop folder even with OneDrive/localized folders |
| `launcher.pyw` | What the shortcut runs each time: starts the server hidden, opens the browser, and stops the server with `--stop` |
| `assets/claude-monitor.ico` | The shortcut icon (Windows shortcuts only accept `.ico`, not `.png`) |
| `.gitattributes` | Keeps `install.bat` on CRLF line endings; without it `cmd.exe` misreads the file |

> `install.bat` is only a simple double-click entry point. The real work (creating the shortcuts) is done by `install_windows.py`.

**If `install.bat` does not work on your machine** (the window closes, it shows an error, or no shortcut appears), install with Python directly:

1. Install Python 3.8+ from [python.org](https://www.python.org/downloads/).
2. In the project folder, type `cmd` in the Explorer address bar and press Enter (or open CMD/PowerShell there).
3. Run:
   ```bat
   py -3 install_windows.py
   ```
   (or `python install_windows.py` if you have no `py`). Run it from CMD rather than double-clicking, because a double-clicked window closes when the script ends and you would not see any error message.
4. Once the shortcut exists, use it from the Desktop or Start Menu as usual.

If no shortcut can be created at all, you can still run without installing anything: `py -3 launcher.pyw` (starts the server hidden and opens the dashboard), or the manual method (Option C) below.

> Windows prerequisite: Python 3.8+ from [python.org](https://www.python.org/downloads/). "Add python.exe to PATH" is not required (the installer also finds it through the `py` launcher), but on a PC without Python, Windows 10/11 may offer a Microsoft Store shortcut for `python` — that is only a stub and is not enough. Check with `py -3 --version`.

#### Option C) Run manually (any OS)

If you'd rather not use the install script:

```bash
cd server
python3 server.py
```

Then open `http://localhost:8765` in your browser.

### Step 3: Verify the connection

1. Open a new tab on claude.ai and log in.
2. Send a message to Claude, or open the Usage page.
3. Go back to the dashboard (`http://localhost:8765`) and refresh; a card for that account should appear with the label you chose.
4. If nothing shows up, open the browser console on the claude.ai tab (press F12) and look for `[ClaudeMonitor:...]` log lines to spot the error (usually means the server isn't running).

---

## Updating

Whenever you replace the project with a newer version:

1. Stop the server (`py -3 launcher.pyw --stop` on Windows, `pkill -f "python3 server.py"` on Linux) and start it again from the shortcut/icon, because `server.py` changed.
2. Click **Reload** on the extension in `chrome://extensions` (or `edge://extensions`) and refresh your `claude.ai` tabs, because `content.js` changed.
3. Do not overwrite or delete `server/status.json` (your history).

## Stopping and uninstalling

- **Stop the server:** as above (`launcher.pyw --stop` on Windows).
- **Uninstall on Windows:** delete both `Claude Monitor.lnk` files (Desktop and Start Menu → Programs), then delete the project folder.
- **Uninstall on Linux:** delete `~/.local/share/applications/claude-monitor.desktop`, the copy on your Desktop, and `claude-monitor-launch.sh` in the project folder.
- **Remove the extension:** click **Remove** in `chrome://extensions`.
- **Data:** everything lives in `server/status.json`. Back it up first if you want to keep your history.

---

## FAQ

**Does this violate Anthropic's terms?**
This tool only reads your own accounts' usage data, available through your already-logged-in browser session; it does not bypass rate limits or automate message sending. Complying with Anthropic's Usage Policy is the user's own responsibility.

**Why does port 8765 need to stay open?**
The server and extension only talk to each other over `localhost:8765`. If that port is taken by another app, change the number to the same value in **all** of these places:

- `server/server.py` (`PORT`)
- `extension/manifest.json` and `extension/background.js`
- `launcher.pyw` (`PORT`, Windows)
- `install.sh` (`PORT`, Linux; run `bash install.sh` again afterwards)

Then reload the extension and restart the server.

**Where is the data stored?**
In `server/status.json`, next to the server itself, as plain JSON — entirely on your machine. It contains your chat text, so don't share it or commit/zip it (it is in `.gitignore`).

If the file ever becomes unreadable, the server does not discard it: it keeps a copy named `status.json.corrupt-<date-time>` next to it so you can recover your data.

**Why do I get `403 forbidden` from the server or the extension?**
By design. The server only accepts requests whose `Host` is `localhost:8765` or `127.0.0.1:8765` and that come from the dashboard itself or the extension (or have no `Origin`, e.g. typing the address in the browser). Opening the dashboard via a LAN IP or another hostname, or requests from other websites, are rejected.

**On Windows, the shortcut opens nothing or says the server did not start.**
1) Open the log: type `%TEMP%\claude-monitor.log` in the Explorer address bar. 2) Common causes: port 8765 is used by another program (`netstat -ano | findstr :8765`), or Python was moved/uninstalled — run `install.bat` again. 3) On Linux/macOS, "Address already in use" after stopping the server no longer happens.
