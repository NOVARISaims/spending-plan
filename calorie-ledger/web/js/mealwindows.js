// Client mirror of server/app/windows.py — keeps Today ticking offline.

export function hhmmToMin(hhmm) {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
}

function reopenEntry(dayState, id) {
  return (dayState?.reopened || []).find((r) => r.id === id) || null;
}

export function windowStatus(win, nowMin, settings, dayState) {
  const start = hhmmToMin(win.start);
  const end = hhmmToMin(win.end);
  const opensSoon = Number(settings.opens_soon_min ?? 30);
  const closingSoon = Number(settings.closing_soon_min ?? 15);
  const reopenMin = Number(settings.reopen_min ?? 45);

  const reopen = reopenEntry(dayState, win.id);
  if (reopen && nowMin >= end) {
    let reopenStart = end;
    const ts = new Date(reopen.ts);
    if (!Number.isNaN(ts.getTime())) reopenStart = ts.getHours() * 60 + ts.getMinutes();
    const reopenEnd = reopenStart + reopenMin;
    if (nowMin < reopenEnd) {
      return { status: 'open', reopened: true, countdown_min: reopenEnd - nowMin, countdown_to: 'close' };
    }
  }
  if (nowMin < start - opensSoon) return { status: 'locked', countdown_min: start - nowMin, countdown_to: 'open' };
  if (nowMin < start) return { status: 'opens_soon', countdown_min: start - nowMin, countdown_to: 'open' };
  if (nowMin < end - closingSoon) return { status: 'open', countdown_min: end - nowMin, countdown_to: 'close' };
  if (nowMin < end) return { status: 'closing_soon', countdown_min: end - nowMin, countdown_to: 'close' };
  return { status: 'expired', countdown_min: 0, countdown_to: null };
}

const rescuedIn = (ds, id) => (ds?.rescues || []).filter((r) => r.to === id)
  .reduce((s, r) => s + r.amount, 0);
const rescuedOut = (ds, id) => (ds?.rescues || []).filter((r) => r.from === id)
  .reduce((s, r) => s + r.amount, 0);

export function dayWindows(settings, consumedByMeal, dayState, nowMin) {
  const out = [];
  let expired = 0;
  let current = null;
  let next = null;
  const wins = (settings.windows || []).filter((w) => w.enabled)
    .sort((a, b) => hhmmToMin(a.start) - hhmmToMin(b.start));
  for (const w of wins) {
    const st = windowStatus(w, nowMin, settings, dayState);
    const consumed = Number(consumedByMeal?.[w.id] || 0);
    const allowance = Number(w.allowance || 0) + rescuedIn(dayState, w.id);
    const info = {
      id: w.id, name: w.name || w.id, start: w.start, end: w.end,
      allowance: Math.round(allowance),
      base_allowance: w.allowance || 0,
      rescued_in: Math.round(rescuedIn(dayState, w.id)),
      rescued_out: Math.round(rescuedOut(dayState, w.id)),
      consumed: Math.round(consumed),
      remaining: Math.round(allowance - consumed),
      ...st,
    };
    if (st.status === 'expired') {
      const lost = Math.max(0, allowance - consumed - rescuedOut(dayState, w.id));
      info.expired_kcal = Math.round(lost);
      expired += lost;
    }
    out.push(info);
    if ((st.status === 'open' || st.status === 'closing_soon') && !current) current = info;
    if ((st.status === 'locked' || st.status === 'opens_soon') && !next) next = info;
  }
  return { windows: out, current, next, expired_kcal: Math.round(expired) };
}

export function suggestMeal(settings, nowMin, dayState) {
  if (!settings.structured_mode) {
    if (nowMin < hhmmToMin('11:00')) return 'breakfast';
    if (nowMin < hhmmToMin('15:30')) return 'lunch';
    if (nowMin < hhmmToMin('21:30')) return 'dinner';
    return 'snack';
  }
  const pic = dayWindows(settings, {}, dayState || {}, nowMin);
  if (pic.current) return pic.current.id;
  if (pic.next) return pic.next.id;
  const enabled = (settings.windows || []).filter((w) => w.enabled);
  return enabled.length ? enabled[enabled.length - 1].id : 'snack';
}

// Preview of the override the server will assign (for warning chips in forms).
export function previewOverride(settings, meal, nowMin, dayState, tags, isToday) {
  if (!settings.structured_mode || !isToday) return null;
  const win = (settings.windows || []).find((w) => w.id === meal && w.enabled);
  if (!win) return null;
  const st = windowStatus(win, nowMin, settings, dayState);
  if (st.status === 'open' || st.status === 'closing_soon') {
    return st.reopened ? 'reopened' : null;
  }
  if ((tags || []).includes('low_energy')) return null;
  return 'outside_window';
}

export const STATUS_LABEL = {
  locked: 'Locked',
  opens_soon: 'Opens soon',
  open: 'Open',
  closing_soon: 'Closing soon',
  expired: 'Expired',
};
