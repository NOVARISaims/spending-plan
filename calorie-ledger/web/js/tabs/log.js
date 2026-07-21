// Log tab: all the ways in (quick, search, saved, recipe, restaurant, copy,
// free foods) + the diary browser/editor by date.

import { api, cachedGet } from '../api.js';
import { queueAll } from '../idb.js';
import { dayWindows } from '../mealwindows.js';
import {
  amountSheet, copyPreviousSheet, entryEditSheet, productForm, quickForm,
  recipeForm, recipePortionSheet, savedMealForm, savedMealSheet,
} from '../sheets.js';
import { S } from '../store.js';
import { $, $$, emit, esc, fmtDateNice, h, nowMin, toast, todayStr } from '../util.js';

let selectedDate = todayStr();
let deepLinkMeal = null;

export function setDeepLink({ meal }) {
  deepLinkMeal = meal || null;
}

export async function render(el) {
  el.innerHTML = `
    <div class="grid3">
      <button class="btn ghost" data-add="quick">⚡ Quick</button>
      <button class="btn ghost" data-add="search">🔍 Product</button>
      <button class="btn ghost" data-add="meal">🍱 Saved</button>
      <button class="btn ghost" data-add="recipe">🥘 Recipe</button>
      <button class="btn ghost" data-add="restaurant">🍽 Restaurant</button>
      <button class="btn ghost" data-add="copy">📋 Copy prev.</button>
    </div>
    <div data-slot="freefoods"></div>
    <div data-slot="picker"></div>
    <div class="datenav">
      <button class="btn ghost small" data-nav="-1">‹</button>
      <input type="date" name="diary-date" value="${selectedDate}">
      <button class="btn ghost small" data-nav="1">›</button>
      <button class="btn ghost small" data-nav="0">Today</button>
    </div>
    <div data-slot="diary"><p class="muted">Loading…</p></div>`;

  el.addEventListener('click', onAction);
  $('[name=diary-date]', el).addEventListener('change', (e) => {
    selectedDate = e.target.value || todayStr();
    renderDiary(el);
  });

  renderFreeFoods(el);
  await renderDiary(el);

  if (deepLinkMeal) {
    const meal = deepLinkMeal;
    deepLinkMeal = null;
    quickForm({ prefill: { meal } });
  }
}

function onAction(e) {
  const add = e.target.closest('[data-add]');
  if (add) {
    const kind = add.dataset.add;
    const el = add.closest('.view') || document;
    if (kind === 'quick') quickForm({});
    if (kind === 'restaurant') quickForm({ source: 'restaurant' });
    if (kind === 'copy') copyPreviousSheet({});
    if (kind === 'search') openSearch(el, 'foods');
    if (kind === 'meal') openSearch(el, 'meals');
    if (kind === 'recipe') openSearch(el, 'recipes');
    return;
  }
  const nav = e.target.closest('[data-nav]');
  if (nav) {
    const root = nav.closest('.view');
    const delta = Number(nav.dataset.nav);
    if (delta === 0) selectedDate = todayStr();
    else {
      const d = new Date(selectedDate + 'T12:00:00');
      d.setDate(d.getDate() + delta);
      selectedDate = d.toLocaleDateString('en-CA');
    }
    $('[name=diary-date]', root).value = selectedDate;
    renderDiary(root);
  }
}

// ------------------------------------------------------------ free foods
function renderFreeFoods(el) {
  const slot = $('[data-slot=freefoods]', el);
  const settings = S.settings || {};
  if (!settings.structured_mode) { slot.innerHTML = ''; return; }
  const pic = dayWindows(settings, {}, S.today?.day_state || {}, nowMin());
  if (pic.current) { slot.innerHTML = ''; return; } // windows open: no need
  const foods = settings.low_energy_foods || [];
  if (!foods.length) { slot.innerHTML = ''; return; }
  slot.innerHTML = `
    <div class="card flat" style="margin-top:12px">
      <h3>Free foods (outside windows)</h3>
      <div class="tag-row">${foods.map((f) =>
        `<button class="chip tappable" data-free="${esc(f)}">${esc(f)}</button>`).join('')}</div>
    </div>`;
  slot.onclick = (e) => {
    const b = e.target.closest('[data-free]');
    if (!b) return;
    quickForm({
      prefill: { name: b.dataset.free, calories: 15, tags: ['low_energy', 'vegetables'] },
    });
  };
}

// ---------------------------------------------------------------- search
async function openSearch(root, type) {
  const slot = $('[data-slot=picker]', root);
  const title = { foods: 'Products', meals: 'Saved meals', recipes: 'Recipes' }[type];
  slot.innerHTML = `
    <div class="card" style="margin-top:12px">
      <div class="row between"><h2 style="margin:0">${title}</h2>
        <button class="btn small ghost" data-x="close">✕</button></div>
      <div class="row" style="margin:10px 0">
        <input name="q" placeholder="Search…" autocomplete="off">
        <button class="btn small" data-x="new" style="flex-shrink:0">＋ New</button>
      </div>
      <div data-slot="results" class="pick-list"><p class="muted small">Type to search, or browse most-used below.</p></div>
    </div>`;
  const input = $('[name=q]', slot);
  const results = $('[data-slot=results]', slot);

  const search = async () => {
    const q = input.value.trim();
    const path = { foods: '/api/catalog/foods', meals: '/api/catalog/meals', recipes: '/api/catalog/recipes' }[type];
    let data;
    try {
      data = await api(`${path}?q=${encodeURIComponent(q)}&limit=30`);
    } catch { results.innerHTML = '<p class="muted small">Offline — catalog search needs the server.</p>'; return; }
    const items = data.foods || data.meals || data.recipes || [];
    if (!items.length) {
      results.innerHTML = `<p class="muted small">No matches${q ? ` for “${esc(q)}”` : ''}. Create it once and it's yours.</p>`;
      return;
    }
    results.innerHTML = items.map((it) => {
      const kcal = type === 'recipes'
        ? (it.totals?.per_portion ? `${Math.round(it.totals.per_portion.calories)}/ptn` : `${Math.round(it.totals?.total.calories || 0)} tot`)
        : Math.round(it.calories);
      const sub = type === 'foods'
        ? `${esc(it.brand || '')}${it.brand ? ' · ' : ''}${basisShort(it.basis)}${it.vegan ? ' · vegan' : ''}`
        : type === 'meals' ? `per serving${it.vegan ? ' · vegan' : ''}` : `${(it.ingredients || []).length} ingredients`;
      return `<div class="entry" data-pick="${it.id}">
        <div class="main"><div class="name">${esc(it.name)}</div><div class="sub">${sub}</div></div>
        <div class="kcal">${kcal}</div>
        <button class="btn small ghost" data-edit="${it.id}">✎</button>
      </div>`;
    }).join('');
    results.dataset.items = JSON.stringify(items);
  };
  let deb;
  input.addEventListener('input', () => { clearTimeout(deb); deb = setTimeout(search, 250); });
  await search();
  input.focus();

  slot.onclick = (e) => {
    if (e.target.closest('[data-x=close]')) { slot.innerHTML = ''; slot.onclick = null; return; }
    if (e.target.closest('[data-x=new]')) {
      const onSaved = () => search();
      if (type === 'foods') productForm({ onSaved });
      if (type === 'meals') savedMealForm({ onSaved });
      if (type === 'recipes') recipeForm({ onSaved });
      return;
    }
    const editBtn = e.target.closest('[data-edit]');
    const pickRow = e.target.closest('[data-pick]');
    if (!editBtn && !pickRow) return;
    const items = JSON.parse(results.dataset.items || '[]');
    const id = (editBtn || pickRow).dataset.edit || pickRow?.dataset.pick;
    const item = items.find((x) => x.id === id);
    if (!item) return;
    if (editBtn) {
      if (type === 'foods') productForm({ food: item, onSaved: search });
      if (type === 'meals') savedMealForm({ meal: item, onSaved: search });
      if (type === 'recipes') recipeForm({ recipe: item, onSaved: search });
    } else {
      if (type === 'foods') amountSheet(item, { source: 'manual_product' });
      if (type === 'meals') savedMealSheet(item, {});
      if (type === 'recipes') recipePortionSheet(item, {});
    }
  };
}

function basisShort(b) {
  return { per_100g: '/100g', per_100ml: '/100ml', per_pack: '/pack', per_item: '/item', per_serving: '/serving' }[b] || '';
}

// ----------------------------------------------------------------- diary
async function renderDiary(root) {
  const slot = $('[data-slot=diary]', root);
  let data;
  let stale = false;
  try {
    const res = await cachedGet(`/api/diary?date=${selectedDate}`);
    data = res.data; stale = res.stale;
  } catch {
    slot.innerHTML = '<div class="card"><p class="muted">Offline — no cached diary for this date.</p></div>';
    return;
  }

  const pendingOps = (await queueAll().catch(() => []))
    .filter((op) => op.entity === 'diary' && op.action === 'create' && op.payload.date === selectedDate);
  const pendingEntries = pendingOps.map((op) => ({ ...op.payload, id: null, pending: true }));
  const entries = [...data.entries, ...pendingEntries];

  const settings = S.settings || {};
  const isToday = selectedDate === todayStr();
  const pic = settings.structured_mode && settings.windows && isToday
    ? dayWindows(settings, {}, S.today?.day_state || {}, nowMin()) : null;

  const groups = { breakfast: [], lunch: [], dinner: [], snack: [] };
  for (const e of entries) (groups[e.meal] || groups.snack).push(e);
  const totalKcal = entries.reduce((s, e) => s + (e.calories || 0), 0);

  let html = `<div class="row between" style="margin:2px 0 6px">
    <h2 style="margin:0">${fmtDateNice(selectedDate)}</h2>
    <span class="muted">${Math.round(totalKcal)} kcal${stale ? ' · offline' : ''}</span></div>`;

  for (const [meal, list] of Object.entries(groups)) {
    const win = pic?.windows.find((w) => w.id === meal);
    const mealKcal = list.reduce((s, e) => s + (e.calories || 0), 0);
    html += `<div class="meal-head"><h2>${meal[0].toUpperCase() + meal.slice(1)}</h2>
      ${win ? `<span class="chip st-${win.status}">${win.start}–${win.end}</span>` : ''}
      <span class="tot">${Math.round(mealKcal)}${win ? ` / ${win.allowance}` : ''} kcal</span></div>`;
    if (!list.length) {
      html += '<p class="muted small" style="margin:2px 0 8px">Nothing logged.</p>';
      continue;
    }
    html += '<div class="card flat">';
    for (const e of list) {
      const chips = [];
      if (e.pending) chips.push('<span class="chip warn">pending</span>');
      if (e.override) chips.push(`<span class="chip warn">${e.override.replace(/_/g, ' ')}</span>`);
      if (e.accuracy === 'rough_estimate') chips.push('<span class="chip">rough</span>');
      if (e.favourite) chips.push('<span class="chip">★</span>');
      html += `<div class="entry" ${e.id ? `data-entry="${e.id}"` : ''}>
        <div class="main"><div class="name">${esc(e.name)}</div>
          <div class="sub">${e.time} · ${amountLabel(e)}${chips.length ? ' ' : ''}${chips.join(' ')}</div></div>
        <div class="kcal">${Math.round(e.calories)}</div>
      </div>`;
    }
    html += '</div>';
  }
  slot.innerHTML = html;
  slot.dataset.entries = JSON.stringify(data.entries);

  slot.onclick = (e) => {
    const rowEl = e.target.closest('[data-entry]');
    if (!rowEl) return;
    const all = JSON.parse(slot.dataset.entries || '[]');
    const entry = all.find((x) => x.id === rowEl.dataset.entry);
    if (entry) entryEditSheet(entry, { onDone: () => renderDiary(root) });
  };
}

function amountLabel(e) {
  if (!e.amount_mode || e.amount_mode === 'direct') return e.source.replace(/_/g, ' ');
  const u = { grams: 'g', ml: 'ml', servings: ' srv', items: ' pc', portion: ' ptn' };
  if (e.amount_mode === 'whole_pack') return 'whole pack';
  if (e.amount_mode === 'fraction') return `${e.amount}× pack`;
  return `${e.amount}${u[e.amount_mode] ?? ''}`;
}
