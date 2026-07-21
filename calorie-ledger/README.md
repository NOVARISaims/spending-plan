# Calorie Ledger

A private, single-user, iPhone-first PWA for tracking calories, optional
macros, weight, waist and optional steps — served from your own Windows PC
and reachable **only over your Tailscale tailnet**. No accounts, no social
features, no external food/barcode APIs, no cloud.

```
iPhone (Safari / Home Screen PWA)
   │  HTTPS via `tailscale serve` (tailnet-only, never Funnel)
   ▼
Windows PC — FastAPI (uvicorn on 127.0.0.1:8010)
   ├── SQLite            source of truth (server/data/ledger.sqlite3)
   ├── journal.ndjson    append-only mutation journal (never rewritten)
   ├── CalorieLedger.xlsx  hidden Excel mirror via openpyxl (backup/reading only)
   └── backups/          zipped daily + manual backups, rotated
```

The browser never edits the Excel file. Every write goes through the API into
SQLite; the workbook is regenerated from SQLite (debounced) and included in
backups. Soft deletes everywhere, UUIDs everywhere, and every change lands in
an AuditLog with old + new values.

---

## 1. Set up the server (Windows PC)

1. Install [Python 3.11+](https://www.python.org/downloads/windows/) (tick
   *Add python.exe to PATH*).
2. Copy/clone this repository onto the PC, open `calorie-ledger\server\`.
3. Double-click **`install-windows.bat`** (creates `.venv`, installs
   FastAPI, uvicorn, openpyxl, pywebpush).
4. Optional but recommended — set your own passphrase before first start:
   `setx CALORIE_LEDGER_PASSPHRASE "your-long-passphrase"` (new terminal
   afterwards). Otherwise a random passphrase is generated and written to
   `server\data\FIRST_RUN_PASSPHRASE.txt` on first run.
5. Double-click **`start-windows.bat`**. The server listens on
   `http://127.0.0.1:8010` — loopback only, invisible to your LAN.

Environment overrides: `CALORIE_LEDGER_HOST`, `CALORIE_LEDGER_PORT`,
`CALORIE_LEDGER_DATA` (data directory), `CALORIE_LEDGER_SESSION_DAYS`.

**Auto-start:** Task Scheduler → Create Task → trigger *At log on* → action
*Start a program* → `...\server\start-windows.bat` (tick "Run whether user is
logged on or not" if you want it headless).

## 2. Expose it on your tailnet (HTTPS, no public exposure)

Install [Tailscale](https://tailscale.com) on the PC and on the iPhone
(same tailnet). Then on the PC:

```powershell
tailscale serve --bg http://127.0.0.1:8010
tailscale serve status     # shows https://<machine>.<tailnet>.ts.net
```

(Older Tailscale CLIs: `tailscale serve https / http://127.0.0.1:8010`.)

- `tailscale serve` terminates TLS with a certificate for your MagicDNS name
  and is reachable **from your tailnet only**.
- **Never run `tailscale funnel`** for this app — Funnel publishes to the
  open internet. The app itself also binds to 127.0.0.1, so even a stray
  firewall rule exposes nothing.
- HTTPS matters: service workers, Add-to-Home-Screen and Web Push all
  require a secure context.

## 3. Install on the iPhone

1. In Safari open `https://<machine>.<tailnet>.ts.net`.
2. Log in with your passphrase (Settings → Security → change it any time).
3. Share sheet → **Add to Home Screen** → the app installs as **Ledger**
   with the dark gauge icon, full-screen with safe-area support.
4. For notifications (iOS 16.4+): open the Home-Screen app → Settings →
   *Enable push on this device* → allow.

Tailscale's VPN toggle must be on for the app to reach the server; when it
isn't, the app still opens and queues your logs offline.

---

## Feature map

**Targets** — fixed daily calorie target plus an independent weekly budget
(Settings). Today shows kcal left, eaten/target, weekly balance and pace.

**Structured Meal Mode** (optional, on by default) — editable windows with
per-window allowances: Breakfast 07:00–09:00, Lunch 12:20–13:40, Dinner
17:30–19:00, optional Snack/Reserve. Each window is Locked / Opens Soon /
Open / Closing Soon / Expired with a live countdown and remaining-kcal bar.
Unused calories **expire** and never carry forward. Overrides:

- *Eat outside window* — logging into a closed window is allowed but marked.
- *Reopen missed meal* — grace period (default 45 min) to log late.
- *Rescue meal* — move an expired window's unused kcal into a later window
  today (recorded, auditable).
- Foods on the low-energy "free foods" list (lettuce, celery, cucumber, …,
  editable in Settings) never trigger the outside-window mark.
- A warning banner appears if the day ends unusually low (threshold in
  Settings).

**Logging** — barcode scan (native `BarcodeDetector`, iOS 17+; manual
barcode entry fallback), manual product, quick calories, saved meal, recipe
portion, restaurant/takeaway estimate (accuracy: exact_menu /
good_estimate / rough_estimate), copy previous, favourites. Barcodes are
looked up **only** in your local FoodCatalog; unknown codes create a product
once and it's yours forever. Products support basis per 100 g / 100 ml /
pack / item / serving with pack/serving sizes, live-calculated kcal +
macros, "I ate the whole thing", and remember your last-used amount mode.

**Homemade** — quick estimates, saved meals, and a recipe builder
(ingredients in g/ml with kcal/macros, cooked yield and/or portions →
total kcal, kcal/100 g, kcal/portion).

**Satiety** — local tags (protein, fibre, wholegrain, fruit, vegetables,
low-energy) plus a vegan flag; search prioritises vegan foods (toggle).
Structured meals nudge for one protein + one fibre/produce item.

**Editing** — diary by date grouped into Breakfast/Lunch/Dinner/Snacks;
edit amount, meal, date/time, kcal, macros, accuracy, note; duplicate,
favourite, soft delete with Undo. Editing catalog items with linked history
asks **Future entries only** or **Recalculate N past entries**, shows the
affected row count, requires confirmation, and preserves old values in the
AuditLog. History is never silently changed.

**Body** — weight (kg) and weekly waist (cm) with latest values, 7-day
average and neutral week-on-week trends. Steps are optional, manual or via
Shortcut, and **never** alter calories or allowances.

**Progress** — weight/waist/calorie trends, weekly totals vs budget,
window adherence, missed windows, override counts, steps, and a weekly
review with one practical suggestion.

**Sync** — offline queue in IndexedDB; every mutation is an idempotent op
(UUID) replayed through `/api/sync/batch`, so retries never double-log.
Header chip shows ✓ synced / ↑ pending / ⚠ offline.

## Notifications

Web Push (VAPID keys generated on first run, stored in `server/data/vapid/`)
fires when a window opens, 15 minutes before closing, and at close — with
the remaining allowance in the message and a deep link straight into
logging. Configure per-event toggles in Settings.

> pywebpush needs a C build only rarely; if `install-windows.bat` reports a
> wheel problem, the server still runs — everything works except push.

**iOS Shortcut reminders (optional alternative):** create Personal
Automations at your window times that open
`https://<machine>.ts.net/?tab=log&meal=lunch` (any meal id) — the app
deep-links into logging.

**Steps via Shortcut (optional):** Settings → *Create long-lived Shortcut
token*, then a Shortcut: Find Health Samples (Steps, today) → Get Contents
of URL → POST `https://<machine>.ts.net/api/shortcuts/steps` with header
`Authorization: Bearer <token>` and JSON `{"steps": <count>}`. Run it via a
time-of-day automation.

## Data, backups & restore

- `server/data/ledger.sqlite3` — source of truth (WAL mode).
- `server/data/journal.ndjson` — append-only journal of every mutation.
- `server/data/CalorieLedger.xlsx` — regenerated mirror; sheets for Diary,
  Foods, SavedMeals, Recipes, Weight, Waist, Steps, DayState, AuditLog.
  Open it read-only whenever you like; edits there are overwritten.
- `server/data/backups/ledger-*.zip` — daily (03:00 by default) + manual
  backups containing all three, rotated (keep 40 by default).
- **Restore:** stop the server, unzip a backup, put `ledger.sqlite3` back
  into `server/data/`, start the server. The Excel file regenerates.

## Security notes

- Loopback bind + Tailscale-only TLS; nothing is ever exposed publicly.
- Passphrase stored as salted PBKDF2-SHA256 (240k iterations); login rate
  limited. Tokens are random 256-bit values stored **hashed**, expiring
  after 180 days (sliding), revocable via sign-out.
- API requires `Authorization: Bearer` on every route except `/api/health`.
- Strict CSP (`default-src 'self'`), no third-party requests of any kind.
- The audit log records create/update/soft-delete/recalc with old + new
  values, op id and timestamp.

## Development

```bash
cd calorie-ledger/server
pip install -r requirements-dev.txt
python -m pytest tests/            # 28 tests: window engine, calc, API
python ../tools/make_icons.py      # regenerate icons (needs Pillow)
```

Frontend is dependency-free ES modules in `web/` served by FastAPI — no
build step. When you change any frontend file, bump `VERSION` in `web/sw.js`
so installed PWAs pick it up.
