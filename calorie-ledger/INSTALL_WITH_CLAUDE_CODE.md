# Task for Claude Code: install & launch "Calorie Ledger", then give me my iPhone link

You are Claude Code running **locally on my laptop** (not in the cloud). Install and start
my private **Calorie Ledger** app and finish by printing the HTTPS link I can open on my
iPhone. Work autonomously and only pause when you hit something only I can do (choosing a
passphrase, signing into Tailscale in a browser, approving an HTTPS-cert prompt).

## What this is (context you need)
- A private, single-user PWA served by a small FastAPI backend.
- It must bind to **127.0.0.1 only** and be reachable **only over my Tailscale tailnet**.
- **Never run `tailscale funnel`.** Never expose it to the public internet or bind to
  `0.0.0.0`. Use `tailscale serve` only.
- The code is in my GitHub repo **`novarisaims/spending-plan`**, branch
  **`claude/calorie-ledger-pwa-br5ycs`**, in the **`calorie-ledger/`** folder.
- My previous "Spending Plan" app also lives in this repo at the root — **leave it and any
  files under `calorie-ledger/server/data/` untouched.**

## Step 0 — Detect my OS and check prerequisites
Detect Windows vs macOS vs Linux and use the right commands throughout. Check for `git`,
**Python 3.11+**, and the **Tailscale** CLI. If something is missing, install it if you
reasonably can (winget on Windows, Homebrew on macOS, apt/dnf on Linux); otherwise tell me
exactly what to install and stop. Tailscale CLI locations if it's not on PATH:
- Windows: `C:\Program Files\Tailscale\tailscale.exe`
- macOS (App Store build): `/Applications/Tailscale.app/Contents/MacOS/Tailscale`

## Step 1 — Get the code
- If a `spending-plan` clone already exists here, `cd` into it, then
  `git fetch origin && git checkout claude/calorie-ledger-pwa-br5ycs && git pull`.
- Otherwise clone it: `git clone https://github.com/novarisaims/spending-plan.git`, then
  check out that branch. If the repo is private and the clone fails on auth, use whatever
  GitHub auth I already have (`gh auth login`, or my credential manager) and retry.
- Then `cd calorie-ledger/server`.

## Step 2 — Install the backend
Create a virtualenv and install requirements:
- **Windows:** `py -3 -m venv .venv` → `.venv\Scripts\python -m pip install --upgrade pip`
  → `.venv\Scripts\pip install -r requirements.txt`
- **macOS/Linux:** `python3 -m venv .venv` → `.venv/bin/python -m pip install --upgrade pip`
  → `.venv/bin/pip install -r requirements.txt`

If **`pywebpush` fails to build a wheel**, that is fine and expected on some machines —
install the rest and continue. I only lose Web Push notifications; everything else works.
Fallback: `pip install fastapi "uvicorn[standard]" openpyxl`.

## Step 3 — Set my login passphrase
Ask me for a passphrase (min 8 chars), or generate a strong one and show it to me **once**.
Set it as the environment variable `CALORIE_LEDGER_PASSPHRASE` for the server process.
If you skip this, the server generates one on first run and writes it to
`server/data/FIRST_RUN_PASSPHRASE.txt` — in that case, open that file and show me the value.

## Step 4 — Start the server so it keeps running
Launch it so it survives after you finish this task (not just as a child of your shell):
- **Windows:** open it in its own window — `start "Calorie Ledger" cmd /c start-windows.bat`
  (or `start "" .venv\Scripts\python run.py`).
- **macOS/Linux:** `nohup .venv/bin/python run.py > ../ledger.log 2>&1 &`
It listens on `http://127.0.0.1:8010`. Verify it's up (retry a few times):
`curl -s http://127.0.0.1:8010/api/health` should return JSON with `"ok": true`.

## Step 5 — Make it reachable on my phone via Tailscale
1. `tailscale status` — if it says logged out / needs login, run `tailscale up`, tell me to
   finish the browser sign-in, then continue.
2. Expose the loopback server on my tailnet:
   `tailscale serve --bg http://127.0.0.1:8010`
   - If my CLI rejects that syntax, run `tailscale serve --help` and adapt (older builds use
     `tailscale serve https / http://127.0.0.1:8010`; some use `tailscale serve --bg 8010`).
   - If it prompts to enable HTTPS / MagicDNS certificates, tell me to approve it in the
     Tailscale admin console, then retry.
3. Read my machine's HTTPS URL from `tailscale serve status` (and/or `tailscale status --json`)
   and build the `https://<machine>.<tailnet>.ts.net` address.

## Step 6 — Report back to me, clearly
Print:
1. **My iPhone link** — the `https://….ts.net` URL. Remind me: open it in Safari with the
   Tailscale VPN toggle **on**, log in with my passphrase, then **Share → Add to Home Screen**
   (it installs as "Ledger").
2. **My passphrase** (or the path to `FIRST_RUN_PASSPHRASE.txt`).
3. Whether **push notifications** are available (did `pywebpush` install?).
4. That the server process must stay running for the link to work, and offer to set up
   **auto-start on reboot** if I want it permanent (Windows Task Scheduler pointing at
   `server\start-windows.bat`, or a launchd/systemd service on Mac/Linux).

## Guardrails
- 127.0.0.1 only; never `0.0.0.0`, never `tailscale funnel`, never any public tunnel.
- Don't touch or delete anything in `server/data/` (that's my live data + backups).
- Pause and ask me for any decision only I can make (passphrase, HTTPS-cert approval,
  Tailscale login).
