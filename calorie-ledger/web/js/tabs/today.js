// Today tab: calories left ring, weekly balance, meal windows with live
// countdowns, body metrics, satiety nudges, low-intake warning.

import { cachedGet, mutate } from '../api.js';
import { ring } from '../charts.js';
import { dayWindows } from '../mealwindows.js';
import { bodyLogSheet } from '../sheets.js';
import { S } from '../store.js';
import {
  $, confirmSheet, emit, esc, fmtCountdown, fmtNum, h, nowMin, on, toast, todayStr,
} from '../util.js';
import { queueAll } from '../idb.js';

let tickTimer = null;

export async function render(el) {
  el.innerHTML = '<p class="muted">Loading…</p>';
  let stale = false;
  try {
    const res = await cachedGet(`/api/today`);
    S.today = res.data;
    stale = res.stale;
  } catch {
    el.innerHTML = '<div class="card">Cannot reach the server and no cached data yet.</div>';
    return;
  }
  const t = S.today;

  // Merge offline-queued diary entries for today so numbers stay honest.
  const pending = (await queueAll().catch(() => []))
    .filter((op) => op.entity === 'diary' && op.action === 'create' && op.payload.date === t.date);
  const pendingKcal = pending.reduce((s, op) => s + (op.payload.calories || 0), 0);
  const eaten = t.eaten + pendingKcal;
  const consumed = { ...t.meal_totals };
  for (const op of pending) {
    consumed[op.payload.meal] = (consumed[op.payload.meal] || 0) + (op.payload.calories || 0);
  }

  const settings = S.settings || {};
  const pic = settings.windows
    ? dayWindows(settings, consumed, t.day_state, nowMin())
    : { windows: t.windows, current: t.current_window, next: t.next_window, expired_kcal: t.expired_kcal };

  el.innerHTML = '';
  if (stale) el.appendChild(h('<div class="banner warn">Offline — showing last synced data.</div>'));

  if (t.low_intake_warning && eaten < t.low_intake_kcal) {
    el.appendChild(h(`<div class="banner warn">Intake is unusually low today
      (${Math.round(eaten)} kcal). Fuel matters — a normal dinner beats a rebound tomorrow.</div>`));
  }

  // ---- headline ring + day numbers
  const head = h(`<div class="card"><div class="ring-wrap">
      <div data-slot="ring"></div>
      <div class="today-stats">
        <div class="line"><span class="muted">Eaten / target</span><b>${Math.round(eaten)} / ${t.target}</b></div>
        <div class="line"><span class="muted">Weekly balance</span>
          <b>${t.weekly.balance - pendingKcal >= 0 ? '+' : ''}${Math.round(t.weekly.balance - pendingKcal)}</b></div>
        <div class="line"><span class="muted">Expired today</span><b>${pic.expired_kcal} kcal</b></div>
        ${pending.length ? `<div class="line"><span class="muted">Pending sync</span><b>${pending.length}</b></div>` : ''}
      </div></div></div>`);
  ring($('[data-slot=ring]', head), {
    value: Math.max(0, t.target - eaten), max: t.target,
    label: String(Math.max(0, Math.round(t.target - eaten))), sub: 'kcal left',
  });
  el.appendChild(head);

  // ---- structured windows
  if (t.structured_mode) {
    const current = pic.current;
    if (current) {
      const over = current.consumed > current.allowance;
      const pct = current.allowance > 0
        ? Math.min(100, (current.consumed / current.allowance) * 100) : 0;
      el.appendChild(h(`<div class="card window-card ${current.status === 'closing_soon' ? 'closing' : ''}">
        <div class="row between">
          <h2 style="margin:0">${esc(current.name)}${current.reopened ? ' <span class="chip info">reopened</span>' : ''}</h2>
          <span class="chip st-${current.status}">${current.status === 'closing_soon' ? 'Closing soon' : 'Open'}</span>
        </div>
        <div class="row between" style="margin-top:8px">
          <div><div class="countdown" data-countdown="${current.id}">${fmtCountdown(current.countdown_min)}</div>
            <div class="small muted">until it closes (${current.end})</div></div>
          <div style="text-align:right">
            <div class="stat-v" style="font-size:20px;font-weight:700">${Math.max(0, current.remaining)} kcal</div>
            <div class="small muted">left in window</div></div>
        </div>
        <div class="bar"><i class="${over ? 'over' : ''}" style="width:${pct}%"></i></div>
        ${satietyChips(t, current.id)}
      </div>`));
    } else if (pic.next) {
      el.appendChild(h(`<div class="card window-card">
        <div class="row between">
          <h2 style="margin:0">Next: ${esc(pic.next.name)}</h2>
          <span class="chip st-${pic.next.status}">${pic.next.status === 'opens_soon' ? 'Opens soon' : 'Locked'}</span>
        </div>
        <div class="row between" style="margin-top:8px">
          <div><div class="countdown" data-countdown="${pic.next.id}">${fmtCountdown(pic.next.countdown_min)}</div>
            <div class="small muted">until it opens (${pic.next.start})</div></div>
          <div style="text-align:right">
            <div style="font-size:20px;font-weight:700">${pic.next.allowance} kcal</div>
            <div class="small muted">allowance</div></div>
        </div></div>`));
    } else if (pic.windows.length) {
      el.appendChild(h(`<div class="card window-card expired">
        <h2 style="margin:0">All windows closed</h2>
        <p class="muted small" style="margin:6px 0 0">Unused calories have expired.
        Reopen a meal below if dinner ran late.</p></div>`));
    }

    // all windows overview + override actions
    const list = h('<div class="card"><h3>Meal windows</h3></div>');
    for (const w of pic.windows) {
      const canRescue = w.status === 'expired' && (w.expired_kcal || 0) > 0
        && pic.windows.some((x) => x.status !== 'expired');
      const row = h(`<div class="win-row">
        <div><div class="name">${esc(w.name)}</div>
          <div class="times">${w.start}–${w.end}${w.rescued_in ? ` · +${w.rescued_in} rescued` : ''}</div></div>
        <span class="chip st-${w.status}">${label(w)}</span>
        <div class="kcal">${w.consumed} / ${w.allowance}<br>
          <span class="small muted">${w.status === 'expired' && w.expired_kcal ? `${w.expired_kcal} expired` : `${Math.max(0, w.remaining)} left`}</span></div>
      </div>`);
      const actions = [];
      if (w.status === 'expired') {
        actions.push(`<button class="btn small ghost" data-reopen="${w.id}">Reopen</button>`);
        if (canRescue) actions.push(`<button class="btn small ghost" data-rescue="${w.id}">Rescue</button>`);
      }
      if (actions.length) {
        row.appendChild(h(`<div class="row" style="gap:6px">${actions.join('')}</div>`));
      }
      list.appendChild(row);
    }
    el.appendChild(list);

    list.addEventListener('click', async (e) => {
      const reopenBtn = e.target.closest('[data-reopen]');
      const rescueBtn = e.target.closest('[data-rescue]');
      if (reopenBtn) {
        const id = reopenBtn.dataset.reopen;
        const ok = await confirmSheet({
          title: 'Reopen missed meal?',
          body: `Gives you a ${(S.settings?.reopen_min ?? 45)}-minute grace window to log ${id} late. The entry will be marked "reopened".`,
          okLabel: 'Reopen',
        });
        if (!ok) return;
        const res = await mutate('day', 'reopen', { date: t.date, window_id: id });
        if (res.status !== 'error') { toast('Window reopened'); emit('data-changed'); }
      }
      if (rescueBtn) {
        const from = rescueBtn.dataset.rescue;
        const targets = pic.windows.filter((x) => x.status !== 'expired');
        if (!targets.length) return;
        const chooser = await import('../util.js').then((u) => u.openSheet(`
          <h2>Rescue meal</h2>
          <p class="muted">Move the unused calories from ${esc(from)} into a later window today.</p>
          ${targets.map((x) => `<button class="btn ghost block" style="margin-bottom:8px" data-to="${x.id}">
            → ${esc(x.name)} (${x.start}–${x.end})</button>`).join('')}`));
        chooser.addEventListener('click', async (ev) => {
          const to = ev.target.closest('[data-to]');
          if (!to) return;
          const res = await mutate('day', 'rescue', { date: t.date, from_window: from, to_window: to.dataset.to });
          const { closeSheet } = await import('../util.js');
          closeSheet(chooser);
          if (res.status === 'applied') {
            toast(`Rescued ${res.result.amount} kcal → ${to.dataset.to}`);
            emit('data-changed');
          }
        });
      }
    });
  }

  // ---- body + extras
  const w = t.weight;
  const trend = w.trend_vs_prev_week;
  const trendTxt = trend == null ? '' : ` · ${trend > 0 ? '+' : ''}${fmtNum(trend, 1)} kg vs last wk`;
  el.appendChild(h(`<div class="grid2">
    <button class="stat" data-log="weight" style="text-align:left">
      <div class="v">${w.latest ? fmtNum(w.latest.kg, 1) : '—'} kg</div>
      <div class="l">weight${w.avg7 ? ` · 7d avg ${fmtNum(w.avg7, 1)}${trendTxt}` : ''}</div></button>
    <button class="stat" data-log="waist" style="text-align:left">
      <div class="v">${t.waist.latest ? fmtNum(t.waist.latest.cm, 1) : '—'} cm</div>
      <div class="l">waist${t.waist.latest ? ` · ${t.waist.latest.date}` : ' · tap to log'}</div></button>
    <div class="stat"><div class="v">${fmtNum(t.macros.protein, 0)}g / ${fmtNum(t.macros.fibre, 0)}g</div>
      <div class="l">protein / fibre today</div></div>
    <button class="stat" data-log="steps" style="text-align:left">
      <div class="v">${t.steps != null ? t.steps.toLocaleString() : '—'}</div>
      <div class="l">steps (never changes targets)</div></button>
  </div>`));

  el.addEventListener('click', (e) => {
    const b = e.target.closest('[data-log]');
    if (!b) return;
    const kind = b.dataset.log;
    const latest = kind === 'weight' ? t.weight.latest?.kg
      : kind === 'waist' ? t.waist.latest?.cm : t.steps;
    bodyLogSheet(kind, { latest, onDone: () => emit('data-changed') });
  });

  startTicker(el);
}

function label(w) {
  return {
    locked: 'Locked', opens_soon: 'Opens soon', open: w.reopened ? 'Reopened' : 'Open',
    closing_soon: 'Closing soon', expired: 'Expired',
  }[w.status] || w.status;
}

function satietyChips(t, windowId) {
  if (!t.satiety_nudge) return '';
  const s = t.satiety?.[windowId] || { protein: false, produce: false };
  return `<div class="row" style="margin-top:10px;gap:8px">
    <span class="chip ${s.protein ? 'good' : ''}">${s.protein ? '✓' : '○'} protein</span>
    <span class="chip ${s.produce ? 'good' : ''}">${s.produce ? '✓' : '○'} fibre / produce</span>
    <span class="small muted">aim for one of each</span>
  </div>`;
}

// Re-render countdowns every 30 s without refetching; full refresh on the minute edge.
function startTicker(el) {
  stopTicker();
  let lastMin = nowMin();
  tickTimer = setInterval(() => {
    if (!document.body.contains(el)) { stopTicker(); return; }
    const m = nowMin();
    if (m !== lastMin) {
      lastMin = m;
      emit('render-tab'); // window boundaries move on whole minutes
    }
  }, 15000);
}

export function stopTicker() {
  if (tickTimer) { clearInterval(tickTimer); tickTimer = null; }
}

on('data-changed', () => { /* app.js re-renders the active tab */ });
