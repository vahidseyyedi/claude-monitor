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
- One-click server launch (a desktop icon on Linux, a shortcut on Windows) — no need to open a terminal every time.

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

#### Option B) Windows

1. Place the `install.bat` file (included with this package) in the project's root folder, next to the `server` folder.
2. Double-click it to run (running as administrator is usually not required).
3. This creates a **Claude Monitor** shortcut on your desktop.
4. From now on, double-clicking that shortcut silently starts the server (no visible black console window) and opens the dashboard in your default browser.

> Windows prerequisite: Python must be installed with the **Add python.exe to PATH** option enabled during setup. Check with `python --version` in Command Prompt.

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

## FAQ

**Does this violate Anthropic's terms?**
This tool only reads your own accounts' usage data, available through your already-logged-in browser session; it does not bypass rate limits or automate message sending. Complying with Anthropic's Usage Policy is the user's own responsibility.

**Why does port 8765 need to stay open?**
The server and extension only talk to each other over `localhost:8765`. If that port is taken by another app, change `PORT` in `server/server.py` and update the matching value in `extension/manifest.json` and `extension/background.js`.

**Where is the data stored?**
In `server/status.json`, next to the server itself, as plain JSON — entirely on your machine.
