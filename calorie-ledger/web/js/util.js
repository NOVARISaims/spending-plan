// Small shared helpers: DOM, formatting, sheets, toasts, events.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function h(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export const fmtKcal = (n) => `${Math.round(n ?? 0).toLocaleString()} kcal`;
export const fmtNum = (n, dp = 0) => (n == null ? '—' : Number(n).toFixed(dp));

export function todayStr(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toLocaleDateString('en-CA'); // YYYY-MM-DD in local time
}

export function nowHM() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export function nowMin() {
  const d = new Date();
  return d.getHours() * 60 + d.getMinutes();
}

export function fmtDateNice(iso) {
  const today = todayStr();
  if (iso === today) return 'Today';
  if (iso === todayStr(-1)) return 'Yesterday';
  const d = new Date(iso + 'T12:00:00');
  return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
}

export function fmtCountdown(min) {
  if (min == null) return '';
  if (min >= 60) return `${Math.floor(min / 60)}h ${String(min % 60).padStart(2, '0')}m`;
  return `${min}m`;
}

export const uuid = () =>
  (crypto.randomUUID ? crypto.randomUUID()
    : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
    }));

// ---------------------------------------------------------------- events
const bus = new EventTarget();
export const on = (name, fn) => bus.addEventListener(name, (e) => fn(e.detail));
export const emit = (name, detail) => bus.dispatchEvent(new CustomEvent(name, { detail }));

// ---------------------------------------------------------------- sheets
export function openSheet(innerHtml) {
  const root = $('#sheet-root');
  const backdrop = h(`<div class="backdrop"><div class="sheet" role="dialog" aria-modal="true">
    <div class="grab"></div>${innerHtml}</div></div>`);
  backdrop.addEventListener('click', (e) => { if (e.target === backdrop) closeSheet(backdrop); });
  root.appendChild(backdrop);
  return backdrop;
}

export function closeSheet(el) {
  const target = el || $('#sheet-root').lastElementChild;
  if (target) target.remove();
}

export function confirmSheet({ title, body, okLabel = 'Confirm', danger = false }) {
  return new Promise((resolve) => {
    const sheet = openSheet(`
      <h2>${esc(title)}</h2>
      <p class="muted">${body}</p>
      <div class="frow" style="margin-top:14px">
        <button class="btn ghost block" data-x="no">Cancel</button>
        <button class="btn block ${danger ? 'danger' : ''}" data-x="yes">${esc(okLabel)}</button>
      </div>`);
    sheet.addEventListener('click', (e) => {
      const x = e.target.closest('[data-x]');
      if (!x) return;
      closeSheet(sheet);
      resolve(x.dataset.x === 'yes');
    });
  });
}

// ---------------------------------------------------------------- toasts
export function toast(msg, { bad = false, action, onAction, ms = 3600 } = {}) {
  const root = $('#toast-root');
  const el = h(`<div class="toast ${bad ? 'bad' : ''}"><span>${esc(msg)}</span>
    ${action ? `<button type="button">${esc(action)}</button>` : ''}</div>`);
  if (action) $('button', el).addEventListener('click', () => { el.remove(); onAction?.(); });
  root.appendChild(el);
  setTimeout(() => el.remove(), ms);
}

export function segmented(options, value, onChange) {
  const el = h(`<div class="seg">${options.map((o) =>
    `<button type="button" data-v="${esc(o.value)}" class="${o.value === value ? 'active' : ''}">${esc(o.label)}</button>`
  ).join('')}</div>`);
  el.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    $$('button', el).forEach((x) => x.classList.toggle('active', x === b));
    onChange(b.dataset.v);
  });
  return el;
}
