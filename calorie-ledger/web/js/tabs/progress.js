// Progress tab: weekly review, weight/waist/calorie/steps trends, weekly
// budget, window adherence, overrides.

import { cachedGet } from '../api.js';
import { barChart, lineChart } from '../charts.js';
import { bodyLogSheet } from '../sheets.js';
import { $, emit, esc, fmtNum, h } from '../util.js';

let range = 30;

export async function render(el) {
  el.innerHTML = '<p class="muted">Loading…</p>';
  let progress, review;
  try {
    [progress, review] = await Promise.all([
      cachedGet(`/api/progress?days=${range}`).then((r) => r.data),
      cachedGet('/api/review/weekly').then((r) => r.data).catch(() => null),
    ]);
  } catch {
    el.innerHTML = '<div class="card">Offline and nothing cached yet.</div>';
    return;
  }

  el.innerHTML = '';
  el.appendChild(h(`<div class="row between" style="margin-bottom:10px">
    <h2 style="margin:0">Progress</h2>
    <div class="seg" style="flex:0 0 auto">
      ${[30, 90, 180].map((d) => `<button class="${d === range ? 'active' : ''}" data-range="${d}">${d}d</button>`).join('')}
    </div></div>`));
  el.onclick = (e) => {
    const rangeBtn = e.target.closest('[data-range]');
    if (rangeBtn) { range = Number(rangeBtn.dataset.range); render(el); return; }
    const bodyBtn = e.target.closest('[data-body]');
    if (bodyBtn) bodyLogSheet(bodyBtn.dataset.body, { onDone: () => emit('data-changed') });
  };

  // ---- weekly review
  if (review && review.days_logged > 0) {
    const wd = review.weight_delta_kg;
    el.appendChild(h(`<div class="card">
      <h3>Last week (${review.week_start} → ${review.week_end})</h3>
      <div class="grid3" style="margin:8px 0">
        <div><div class="v" style="font-weight:700">${review.eaten.toLocaleString()}</div><div class="small muted">kcal eaten</div></div>
        <div><div class="v" style="font-weight:700">${review.balance >= 0 ? '+' : ''}${review.balance.toLocaleString()}</div><div class="small muted">vs budget</div></div>
        <div><div class="v" style="font-weight:700">${wd == null ? '—' : `${wd > 0 ? '+' : ''}${fmtNum(wd, 1)} kg`}</div><div class="small muted">7d-avg change</div></div>
        <div><div class="v" style="font-weight:700">${review.days_over_target}</div><div class="small muted">days over target</div></div>
        <div><div class="v" style="font-weight:700">${review.override_count}</div><div class="small muted">overrides</div></div>
        <div><div class="v" style="font-weight:700">${review.steps_avg ? review.steps_avg.toLocaleString() : '—'}</div><div class="small muted">avg steps</div></div>
      </div>
      <p style="margin:4px 0 0"><b>Suggestion:</b> ${esc(review.suggestion)}</p>
    </div>`));
  }

  // ---- weight
  const wCard = h(`<div class="card"><div class="row between"><h3>Weight (kg)</h3>
    <button class="btn small ghost" data-body="weight">＋ Log</button></div><div data-c></div></div>`);
  lineChart($('[data-c]', wCard), {
    series: [
      { points: progress.weights.map((w) => ({ x: w.date, y: w.kg })), color: '#38BDF8', label: 'daily' },
      { points: progress.weight_avg7.map((w) => ({ x: w.date, y: w.kg })), color: '#34D399', width: 2.6, label: '7-day avg' },
    ],
    yFmt: (v) => fmtNum(v, 1),
    empty: 'No weigh-ins yet — tap ＋ Log.',
  });
  el.appendChild(wCard);

  // ---- waist
  const waCard = h(`<div class="card"><div class="row between"><h3>Waist (cm)</h3>
    <button class="btn small ghost" data-body="waist">＋ Log</button></div><div data-c></div></div>`);
  lineChart($('[data-c]', waCard), {
    series: [{ points: progress.waists.map((w) => ({ x: w.date, y: w.cm })), color: '#A78BFA', label: 'weekly waist' }],
    yFmt: (v) => fmtNum(v, 0),
    empty: 'No waist measurements yet — weekly is plenty.',
  });
  el.appendChild(waCard);

  // ---- daily calories
  const cCard = h('<div class="card"><h3>Calories per day</h3><div data-c></div></div>');
  barChart($('[data-c]', cCard), {
    bars: progress.calories.map((c) => ({
      x: c.date, y: c.kcal,
      color: c.kcal > progress.target ? '#FB923C' : '#38BDF8',
    })),
    target: progress.target,
    empty: 'No diary entries in range.',
  });
  cCard.appendChild(h(`<p class="small muted" style="margin:6px 0 0">Dashed line = daily target (${progress.target} kcal).</p>`));
  el.appendChild(cCard);

  // ---- weekly budget
  const wkCard = h('<div class="card"><h3>Weekly total vs budget</h3><div data-c></div></div>');
  barChart($('[data-c]', wkCard), {
    bars: progress.weekly.map((w) => ({
      x: w.week_start, y: w.eaten,
      color: w.eaten > w.budget ? '#FB923C' : '#34D399',
    })),
    target: progress.weekly[0]?.budget,
    empty: 'No complete weeks yet.',
  });
  el.appendChild(wkCard);

  // ---- adherence + overrides
  const ad = progress.adherence || {};
  const adRows = Object.values(ad).map((a) => {
    const pct = a.days ? Math.round((a.hit / a.days) * 100) : 0;
    return `<div class="win-row"><div class="name" style="min-width:86px">${esc(a.name)}</div>
      <div class="bar" style="flex:1;margin:0"><i style="width:${pct}%"></i></div>
      <div class="kcal">${pct}%<br><span class="small muted">${a.missed} missed</span></div></div>`;
  }).join('');
  const ov = progress.overrides || {};
  el.appendChild(h(`<div class="card"><h3>Window adherence (28 days)</h3>
    ${adRows || '<p class="muted small">Enable Structured Meal Mode to track this.</p>'}
    <p class="small muted" style="margin:10px 0 0">Overrides: ${ov.outside_window || 0} outside window ·
    ${ov.reopened || 0} reopened · ${ov.rescue || 0} rescued</p></div>`));

  // ---- steps
  const sCard = h(`<div class="card"><div class="row between"><h3>Steps</h3>
    <button class="btn small ghost" data-body="steps">＋ Log</button></div><div data-c></div></div>`);
  barChart($('[data-c]', sCard), {
    bars: progress.steps.map((s) => ({ x: s.date, y: s.steps, color: '#38BDF8' })),
    yFmt: (v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : String(v)),
    empty: 'No steps yet — optional, and never changes your targets.',
  });
  el.appendChild(sCard);

}
