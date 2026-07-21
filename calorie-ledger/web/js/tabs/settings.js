// Settings tab: targets, meal windows, satiety, notifications, steps
// shortcut, security, data & backups.

import { api, announceSync, flushQueue, getToken, mutate, setToken } from '../api.js';
import { queueCount } from '../idb.js';
import { MEAL_OPTIONS, S } from '../store.js';
import { $, $$, confirmSheet, emit, esc, h, openSheet, closeSheet, toast } from '../util.js';

export async function render(el) {
  const s = S.settings;
  if (!s) { el.innerHTML = '<p class="muted">Loading…</p>'; return; }
  const pending = await queueCount().catch(() => 0);

  el.innerHTML = `
    <h2>Settings</h2>

    <div class="card">
      <h3>Targets</h3>
      <div class="frow">
        <label class="f"><span>Daily target (kcal)</span>
          <input name="daily_target" type="text" inputmode="numeric" value="${s.daily_target}"></label>
        <label class="f"><span>Weekly budget (kcal)</span>
          <input name="weekly_budget" type="text" inputmode="numeric" value="${s.weekly_budget}"></label>
      </div>
      <p class="small muted">Weekly budget is independent — set it to 7× daily or give yourself
      weekend headroom. Unused window calories still expire daily.</p>
      <label class="f"><span>Warn if the day ends under (kcal)</span>
        <input name="low_intake_kcal" type="text" inputmode="numeric" value="${s.low_intake_kcal}"></label>
    </div>

    <div class="card">
      <div class="row between"><h3>Structured Meal Mode</h3>
        <button class="chip tappable ${s.structured_mode ? 'on' : ''}" data-toggle="structured_mode">
          ${s.structured_mode ? 'On' : 'Off'}</button></div>
      <div data-slot="windows" ${s.structured_mode ? '' : 'style="opacity:.45;pointer-events:none"'}>
        ${(s.windows || []).map(winRow).join('')}
        <div class="frow" style="margin-top:8px">
          <label class="f"><span>“Opens soon” lead (min)</span>
            <input name="opens_soon_min" type="text" inputmode="numeric" value="${s.opens_soon_min}"></label>
          <label class="f"><span>“Closing soon” lead (min)</span>
            <input name="closing_soon_min" type="text" inputmode="numeric" value="${s.closing_soon_min}"></label>
        </div>
        <label class="f"><span>Reopen grace (min)</span>
          <input name="reopen_min" type="text" inputmode="numeric" value="${s.reopen_min}"></label>
        <p class="small muted" data-slot="allowance-sum"></p>
      </div>
    </div>

    <div class="card">
      <h3>Satiety &amp; food preferences</h3>
      <div class="row between" style="margin-bottom:8px"><span>Nudge for protein + fibre/produce per meal</span>
        <button class="chip tappable ${s.satiety_nudge ? 'on' : ''}" data-toggle="satiety_nudge">${s.satiety_nudge ? 'On' : 'Off'}</button></div>
      <div class="row between" style="margin-bottom:8px"><span>Prioritise vegan foods in search</span>
        <button class="chip tappable ${s.prioritise_vegan ? 'on' : ''}" data-toggle="prioritise_vegan">${s.prioritise_vegan ? 'On' : 'Off'}</button></div>
      <label class="f"><span>Outside-window “free foods” (one per line)</span>
        <textarea name="low_energy_foods" rows="4">${esc((s.low_energy_foods || []).join('\n'))}</textarea></label>
    </div>

    <div class="card">
      <h3>Notifications</h3>
      <p class="small muted">Requires the app added to your Home Screen (iOS 16.4+), reached over
      HTTPS via <code>tailscale serve</code>.</p>
      <button class="btn ghost block" data-x="enable-push" style="margin:8px 0">Enable push on this device</button>
      <div class="row between" style="margin-bottom:6px"><span>Window opens</span>
        <button class="chip tappable ${s.notifications?.open ? 'on' : ''}" data-notif="open">${s.notifications?.open ? 'On' : 'Off'}</button></div>
      <div class="row between" style="margin-bottom:6px"><span>15 min before closing</span>
        <button class="chip tappable ${s.notifications?.closing ? 'on' : ''}" data-notif="closing">${s.notifications?.closing ? 'On' : 'Off'}</button></div>
      <div class="row between" style="margin-bottom:6px"><span>Window closed</span>
        <button class="chip tappable ${s.notifications?.closed ? 'on' : ''}" data-notif="closed">${s.notifications?.closed ? 'On' : 'Off'}</button></div>
      <button class="btn small ghost" data-x="test-push">Send test notification</button>
      <p class="small muted" style="margin-top:8px">Prefer iOS Shortcuts reminders? Create time-of-day
      automations that open <code>/?tab=log&amp;meal=lunch</code> — see the README.</p>
    </div>

    <div class="card">
      <h3>Steps via iOS Shortcut (optional)</h3>
      <p class="small muted">Steps never change calories or allowances. A Shortcut can POST
      Health steps to <code>/api/shortcuts/steps</code> on your tailnet.</p>
      <button class="btn ghost block" data-x="shortcut-token">Create long-lived Shortcut token</button>
    </div>

    <div class="card">
      <h3>Data &amp; backups</h3>
      <p class="small muted">Sync: <b data-slot="pending">${pending ? `${pending} queued` : 'up to date'}</b></p>
      <div class="grid2">
        <button class="btn ghost" data-x="flush">Sync now</button>
        <button class="btn ghost" data-x="backup">Backup now</button>
        <button class="btn ghost" data-x="excel">Download Excel</button>
        <button class="btn ghost" data-x="audit">Audit log</button>
      </div>
      <div data-slot="backups" class="small muted" style="margin-top:10px"></div>
    </div>

    <div class="card">
      <h3>Security</h3>
      <button class="btn ghost block" data-x="change-pass" style="margin-bottom:8px">Change passphrase</button>
      <button class="btn danger block" data-x="logout">Sign out on this device</button>
    </div>

    <div style="display:flex;justify-content:center;margin:6px 0 0">
      <button class="btn block" data-x="save" style="max-width:320px">Save settings</button>
    </div>
    <p class="small muted" style="text-align:center;margin-top:10px">
      Calorie Ledger · private · Tailscale-only · Excel mirror on your PC</p>`;

  updateAllowanceSum(el, s);
  el.oninput = () => updateAllowanceSum(el, collect(el, s));
  el.onclick = (e) => onClick(e, el);
  loadBackups(el);
}

function winRow(w) {
  return `<div class="card flat" data-win="${w.id}" style="margin-bottom:8px">
    <div class="row between" style="margin-bottom:6px">
      <b>${esc(w.name)}</b>
      <button class="chip tappable ${w.enabled ? 'on' : ''}" data-win-toggle="${w.id}">${w.enabled ? 'On' : 'Off'}</button>
    </div>
    <div class="frow">
      <label class="f"><span>Opens</span><input data-w="start" type="time" value="${w.start}"></label>
      <label class="f"><span>Closes</span><input data-w="end" type="time" value="${w.end}"></label>
      <label class="f"><span>kcal</span><input data-w="allowance" type="text" inputmode="numeric" value="${w.allowance}"></label>
    </div>
  </div>`;
}

function collect(el, base) {
  const num = (name, fallback) => {
    const v = parseFloat($(`[name=${name}]`, el)?.value);
    return Number.isNaN(v) ? fallback : v;
  };
  const windows = $$('[data-win]', el).map((row) => {
    const id = row.dataset.win;
    const old = (base.windows || []).find((w) => w.id === id) || {};
    return {
      id,
      name: old.name || id,
      start: $('[data-w=start]', row).value || old.start,
      end: $('[data-w=end]', row).value || old.end,
      allowance: parseFloat($('[data-w=allowance]', row).value) || 0,
      enabled: $(`[data-win-toggle="${id}"]`, row).classList.contains('on'),
    };
  });
  return {
    ...base,
    daily_target: num('daily_target', base.daily_target),
    weekly_budget: num('weekly_budget', base.weekly_budget),
    low_intake_kcal: num('low_intake_kcal', base.low_intake_kcal),
    opens_soon_min: num('opens_soon_min', base.opens_soon_min),
    closing_soon_min: num('closing_soon_min', base.closing_soon_min),
    reopen_min: num('reopen_min', base.reopen_min),
    windows: windows.length ? windows : base.windows,
    low_energy_foods: ($('[name=low_energy_foods]', el)?.value || '')
      .split('\n').map((x) => x.trim()).filter(Boolean),
  };
}

function updateAllowanceSum(el, s) {
  const slot = $('[data-slot=allowance-sum]', el);
  if (!slot) return;
  const sum = (s.windows || []).filter((w) => w.enabled)
    .reduce((acc, w) => acc + (Number(w.allowance) || 0), 0);
  const diff = s.daily_target - sum;
  slot.textContent = `Enabled window allowances total ${sum} kcal · daily target ${s.daily_target} kcal`
    + (diff === 0 ? ' · matched' : diff > 0 ? ` · ${diff} unallocated` : ` · ${-diff} over target`);
}

async function onClick(e, el) {
  const s = S.settings;
  const toggle = e.target.closest('[data-toggle]');
  if (toggle) {
    const key = toggle.dataset.toggle;
    s[key] = !s[key];
    toggle.classList.toggle('on', s[key]);
    toggle.textContent = s[key] ? 'On' : 'Off';
    if (key === 'structured_mode') render(el);
    return;
  }
  const winToggle = e.target.closest('[data-win-toggle]');
  if (winToggle) {
    winToggle.classList.toggle('on');
    winToggle.textContent = winToggle.classList.contains('on') ? 'On' : 'Off';
    return;
  }
  const notif = e.target.closest('[data-notif]');
  if (notif) {
    const key = notif.dataset.notif;
    s.notifications = { ...s.notifications, [key]: !s.notifications?.[key] };
    notif.classList.toggle('on', s.notifications[key]);
    notif.textContent = s.notifications[key] ? 'On' : 'Off';
    return;
  }

  const x = e.target.closest('[data-x]');
  if (!x) return;
  switch (x.dataset.x) {
    case 'save': {
      const data = collect(el, s);
      const res = await mutate('settings', 'update', {
        daily_target: data.daily_target, weekly_budget: data.weekly_budget,
        low_intake_kcal: data.low_intake_kcal, structured_mode: data.structured_mode,
        windows: data.windows, opens_soon_min: data.opens_soon_min,
        closing_soon_min: data.closing_soon_min, reopen_min: data.reopen_min,
        satiety_nudge: data.satiety_nudge, prioritise_vegan: data.prioritise_vegan,
        low_energy_foods: data.low_energy_foods, notifications: data.notifications,
      });
      if (res.status === 'applied') {
        S.settings = { ...s, ...data };
        toast('Settings saved');
        emit('data-changed');
      } else if (res.status === 'queued') {
        toast('Saved offline — will sync');
      }
      break;
    }
    case 'flush':
      await flushQueue();
      await announceSync();
      $('[data-slot=pending]', el).textContent =
        (await queueCount().catch(() => 0)) ? 'still queued (offline?)' : 'up to date';
      toast('Sync attempted');
      break;
    case 'backup': {
      try {
        const r = await api('/api/backups/run', { method: 'POST', body: {} });
        toast(`Backup created: ${r.file}`);
        loadBackups(el);
      } catch (err) { toast(err.message || 'Backup failed', { bad: true }); }
      break;
    }
    case 'excel': {
      try {
        const res = await fetch('/api/export/excel/file', {
          headers: { Authorization: `Bearer ${getToken()}` },
        });
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'CalorieLedger.xlsx'; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
      } catch (err) { toast(err.message || 'Export failed', { bad: true }); }
      break;
    }
    case 'audit': {
      try {
        const r = await api('/api/audit?limit=60');
        openSheet(`<h2>Audit log</h2><div class="pick-list">${r.audit.map((a) => `
          <div class="entry"><div class="main">
            <div class="name">${esc(a.entity)} · ${esc(a.action)}</div>
            <div class="sub">${a.ts}${a.entity_id ? ` · ${a.entity_id.slice(0, 8)}` : ''}</div>
          </div></div>`).join('') || '<p class="muted">Empty.</p>'}</div>`);
      } catch { toast('Need the server for this', { bad: true }); }
      break;
    }
    case 'enable-push': await enablePush(); break;
    case 'test-push':
      try {
        const r = await api('/api/push/test', { method: 'POST', body: {} });
        toast(r.sent ? `Sent to ${r.sent} device(s)` : 'No subscribed devices yet', { bad: !r.sent });
      } catch (err) { toast(err.message, { bad: true }); }
      break;
    case 'shortcut-token': {
      try {
        const r = await api('/api/auth/shortcut-token', { method: 'POST', body: {} });
        openSheet(`<h2>Shortcut token</h2>
          <p class="muted small">Use in an iOS Shortcut: “Get Contents of URL” → POST
          <code>https://&lt;your-machine&gt;.ts.net/api/shortcuts/steps</code>, header
          <code>Authorization: Bearer &lt;token&gt;</code>, JSON body <code>{"steps": [Health steps]}</code>.
          Valid ~2 years. Shown once:</p>
          <textarea rows="3" readonly>${esc(r.token)}</textarea>
          <button class="btn block" data-copy-token style="margin-top:10px">Copy token</button>`);
        $('#sheet-root [data-copy-token]')?.addEventListener('click', async (ev) => {
          await navigator.clipboard?.writeText(r.token).catch(() => {});
          ev.target.textContent = 'Copied ✓';
        });
      } catch (err) { toast(err.message, { bad: true }); }
      break;
    }
    case 'change-pass': changePassSheet(); break;
    case 'logout': {
      const ok = await confirmSheet({ title: 'Sign out?', body: 'You will need the passphrase to sign back in.', okLabel: 'Sign out', danger: true });
      if (!ok) return;
      await api('/api/auth/logout', { method: 'POST', body: {} }).catch(() => {});
      setToken(null);
      location.reload();
      break;
    }
  }
}

async function loadBackups(el) {
  const slot = $('[data-slot=backups]', el);
  if (!slot) return;
  try {
    const r = await api('/api/backups');
    const list = r.backups.slice(0, 3);
    slot.innerHTML = list.length
      ? `Latest backups:<br>${list.map((b) => `${b.file} (${Math.round(b.size / 1024)} KB)`).join('<br>')}`
      : 'No backups yet — automatic daily backup runs on the server.';
  } catch { slot.textContent = ''; }
}

async function enablePush() {
  try {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      toast('Push not supported here. On iPhone: add to Home Screen first.', { bad: true });
      return;
    }
    const reg = await navigator.serviceWorker.ready;
    const perm = await Notification.requestPermission();
    if (perm !== 'granted') { toast('Notification permission denied', { bad: true }); return; }
    const { key } = await api('/api/push/key');
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlB64ToUint8(key),
    });
    await api('/api/push/subscribe', { method: 'POST', body: sub.toJSON() });
    toast('Push enabled on this device');
  } catch (err) {
    toast(err.message || 'Push setup failed', { bad: true, ms: 5000 });
  }
}

function urlB64ToUint8(b64) {
  const pad = '='.repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

function changePassSheet() {
  const sheet = openSheet(`
    <h2>Change passphrase</h2>
    <label class="f"><span>Current</span><input name="cur" type="password" autocomplete="current-password"></label>
    <label class="f"><span>New (min 8 chars)</span><input name="new" type="password" autocomplete="new-password"></label>
    <button class="btn block" data-x="go">Change</button>`);
  $('[data-x=go]', sheet).addEventListener('click', async () => {
    const current = $('[name=cur]', sheet).value;
    const next = $('[name=new]', sheet).value;
    if (next.length < 8) { toast('New passphrase too short', { bad: true }); return; }
    try {
      await api('/api/auth/change-passphrase', { method: 'POST', body: { current, new: next } });
      toast('Passphrase changed');
      closeSheet(sheet);
    } catch (err) { toast(err.message, { bad: true }); }
  });
}
