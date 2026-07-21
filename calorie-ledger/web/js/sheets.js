// Shared bottom-sheet flows: amount picker, product / quick / saved-meal /
// recipe forms, diary entry editor, copy-previous. Used by Scan and Log tabs.

import { api, mutate } from './api.js';
import {
  MACROS, availableModes, foodNutrition, mealNutrition,
  recipeNutrition, recipeTotals,
} from './calc.js';
import { previewOverride, suggestMeal } from './mealwindows.js';
import { ACCURACY_OPTIONS, MEAL_OPTIONS, S, TAG_OPTIONS } from './store.js';
import {
  $, $$, closeSheet, confirmSheet, emit, esc, fmtNum, h, nowHM, nowMin,
  openSheet, segmented, toast, todayStr,
} from './util.js';

const MODE_UNITS = {
  grams: 'g', ml: 'ml', fraction: 'of pack', servings: 'servings',
  items: 'items', portion: 'portions', whole_pack: '',
};

function macroLine(n) {
  const parts = [];
  if (n.protein != null) parts.push(`P ${fmtNum(n.protein, 1)}g`);
  if (n.carbs != null) parts.push(`C ${fmtNum(n.carbs, 1)}g`);
  if (n.fat != null) parts.push(`F ${fmtNum(n.fat, 1)}g`);
  if (n.fibre != null) parts.push(`Fb ${fmtNum(n.fibre, 1)}g`);
  return parts.join(' · ');
}

function mealSelect(value) {
  return `<label class="f"><span>Meal / window</span>
    <select name="meal">${MEAL_OPTIONS.map((m) =>
      `<option value="${m.value}" ${m.value === value ? 'selected' : ''}>${m.label}</option>`).join('')}
    </select></label>`;
}

function overrideChip(meal, tags, date) {
  const ov = previewOverride(S.settings || {}, meal, nowMin(),
    S.today?.day_state, tags, date === todayStr());
  if (ov === 'outside_window') {
    return '<span class="chip warn">Outside window — will be marked</span>';
  }
  if (ov === 'reopened') return '<span class="chip info">Reopened window</span>';
  return '';
}

async function submitDiary(fields, { quiet = false } = {}) {
  const res = await mutate('diary', 'create', fields);
  if (res.status === 'queued') {
    toast('Saved offline — will sync when connected');
  } else if (res.status === 'applied') {
    const kcal = Math.round(res.result?.calories ?? fields.calories);
    if (!quiet) toast(`Logged ${fields.name} — ${kcal} kcal`);
    if (res.result?.override === 'outside_window') {
      toast('Marked as outside window', { ms: 2600 });
    }
  }
  emit('data-changed');
  return res;
}

// ---------------------------------------------------------------- amount
// The "how much of this product" sheet, incl. "I ate the whole thing".
export function amountSheet(food, { source = 'manual_product', meal, onDone } = {}) {
  const modes = availableModes(food);
  if (!modes.length) { toast('Product has no usable amounts', { bad: true }); return; }
  let mode = modes.some((m) => m.mode === food.last_amount_mode)
    ? food.last_amount_mode : modes[0].mode;
  let amount = defaultAmount(food, mode);
  let chosenMeal = meal || suggestMeal(S.settings || {}, nowMin(), S.today?.day_state);

  const whole = modes.find((m) => m.mode === 'whole_pack');
  const sheet = openSheet(`
    <h2>${esc(food.name)}</h2>
    <p class="muted small">${esc(food.brand || '')}${food.brand ? ' · ' : ''}${basisLabel(food)}
      ${food.vegan ? ' · <span class="chip good">vegan</span>' : ''}</p>
    ${whole ? '<button class="btn block" data-x="whole">I ate the whole thing</button>' : ''}
    <div style="margin:14px 0 8px" data-slot="modes"></div>
    <div class="frow">
      <label class="f" data-slot="amount-wrap"><span data-slot="amount-label">Amount</span>
        <input name="amount" type="text" inputmode="decimal" value="${amount}"></label>
    </div>
    <div class="kcal-preview"><div class="v" data-slot="kcal">–</div>
      <div class="m" data-slot="macros"></div></div>
    ${mealSelect(chosenMeal)}
    <div data-slot="override"></div>
    <details class="adv"><summary>Date &amp; time</summary>
      <div class="frow">
        <label class="f"><span>Date</span><input name="date" type="date" value="${todayStr()}"></label>
        <label class="f"><span>Time</span><input name="time" type="time" value="${nowHM()}"></label>
      </div>
    </details>
    <button class="btn block" data-x="log">Log it</button>`);

  const seg = segmented(modes.map((m) => ({ value: m.mode, label: m.label })), mode, (v) => {
    mode = v;
    amount = defaultAmount(food, mode);
    const input = $('[name=amount]', sheet);
    input.value = amount;
    input.closest('label').style.display = mode === 'whole_pack' ? 'none' : '';
    update();
  });
  $('[data-slot=modes]', sheet).appendChild(seg);
  if (mode === 'whole_pack') $('[name=amount]', sheet).closest('label').style.display = 'none';

  function update() {
    amount = parseFloat($('[name=amount]', sheet).value) || (mode === 'whole_pack' ? 1 : 0);
    let n;
    try { n = foodNutrition(food, mode, amount); } catch { n = { calories: NaN }; }
    $('[data-slot=kcal]', sheet).textContent =
      Number.isNaN(n.calories) ? '—' : `${Math.round(n.calories)} kcal`;
    $('[data-slot=macros]', sheet).textContent = Number.isNaN(n.calories) ? '' : macroLine(n);
    $('[data-slot=amount-label]', sheet).textContent =
      `Amount ${MODE_UNITS[mode] ? `(${MODE_UNITS[mode]})` : ''}`;
    $('[data-slot=override]', sheet).innerHTML =
      overrideChip(chosenMeal, food.tags, $('[name=date]', sheet).value);
  }
  sheet.addEventListener('input', (e) => {
    if (e.target.name === 'meal') chosenMeal = e.target.value;
    update();
  });
  update();

  sheet.addEventListener('click', async (e) => {
    const x = e.target.closest('[data-x]');
    if (!x) return;
    const logMode = x.dataset.x === 'whole' ? 'whole_pack' : mode;
    const logAmount = x.dataset.x === 'whole' ? 1
      : (mode === 'whole_pack' ? 1 : parseFloat($('[name=amount]', sheet).value));
    if (logMode !== 'whole_pack' && (!logAmount || logAmount <= 0)) {
      toast('Enter an amount', { bad: true }); return;
    }
    let n;
    try { n = foodNutrition(food, logMode, logAmount); } catch { n = { calories: 0 }; }
    x.disabled = true;
    await submitDiary({
      date: $('[name=date]', sheet).value, time: $('[name=time]', sheet).value,
      meal: $('[name=meal]', sheet).value, source,
      ref_type: 'food', ref_id: food.id, name: food.name, brand: food.brand,
      amount_mode: logMode, amount: logAmount,
      calories: n.calories || 0, protein: n.protein, carbs: n.carbs,
      fat: n.fat, fibre: n.fibre, tags: food.tags || [],
    });
    closeSheet(sheet);
    onDone?.();
  });
}

function defaultAmount(food, mode) {
  if (mode === 'whole_pack') return 1;
  if (food.last_amount_mode === mode && food.last_amount) return food.last_amount;
  if (mode === 'grams') return food.serving_g || 100;
  if (mode === 'ml') return 100;
  if (mode === 'fraction') return 0.5;
  return 1;
}

function basisLabel(food) {
  const map = {
    per_100g: 'per 100 g', per_100ml: 'per 100 ml', per_pack: 'per pack',
    per_item: 'per item', per_serving: 'per serving',
  };
  return `${Math.round(food.calories)} kcal ${map[food.basis] || ''}`;
}

// --------------------------------------------------------------- product
export function productForm({ food, barcode, onSaved } = {}) {
  const f = food || {};
  const isEdit = !!food;
  const tags = new Set(f.tags || []);
  const sheet = openSheet(`
    <h2>${isEdit ? 'Edit product' : 'New product'}</h2>
    <label class="f"><span>Name</span><input name="name" value="${esc(f.name || '')}" required></label>
    <div class="frow">
      <label class="f"><span>Brand (optional)</span><input name="brand" value="${esc(f.brand || '')}"></label>
      <label class="f"><span>Barcode</span><input name="barcode" inputmode="numeric"
        value="${esc(f.barcode || barcode || '')}"></label>
    </div>
    <label class="f"><span>Calorie basis</span>
      <select name="basis">
        ${['per_100g', 'per_100ml', 'per_pack', 'per_item', 'per_serving'].map((b) =>
          `<option value="${b}" ${f.basis === b ? 'selected' : ''}>${
            { per_100g: 'Per 100 g', per_100ml: 'Per 100 ml', per_pack: 'Per pack', per_item: 'Per item', per_serving: 'Per serving' }[b]
          }</option>`).join('')}
      </select></label>
    <label class="f"><span data-slot="kcal-label">Calories</span>
      <input name="calories" type="text" inputmode="decimal" value="${f.calories ?? ''}" required></label>
    <div class="frow">
      <label class="f"><span>Pack size (g)</span><input name="pack_g" type="text" inputmode="decimal" value="${f.pack_g ?? ''}"></label>
      <label class="f"><span>Pack size (ml)</span><input name="pack_ml" type="text" inputmode="decimal" value="${f.pack_ml ?? ''}"></label>
    </div>
    <div class="frow">
      <label class="f"><span>Serving (g)</span><input name="serving_g" type="text" inputmode="decimal" value="${f.serving_g ?? ''}"></label>
      <label class="f"><span>Items per pack</span><input name="items_per_pack" type="text" inputmode="decimal" value="${f.items_per_pack ?? ''}"></label>
    </div>
    <details class="adv" ${f.protein != null ? 'open' : ''}><summary>Macros (per basis, optional)</summary>
      <div class="frow">
        <label class="f"><span>Protein g</span><input name="protein" type="text" inputmode="decimal" value="${f.protein ?? ''}"></label>
        <label class="f"><span>Carbs g</span><input name="carbs" type="text" inputmode="decimal" value="${f.carbs ?? ''}"></label>
      </div>
      <div class="frow">
        <label class="f"><span>Fat g</span><input name="fat" type="text" inputmode="decimal" value="${f.fat ?? ''}"></label>
        <label class="f"><span>Fibre g</span><input name="fibre" type="text" inputmode="decimal" value="${f.fibre ?? ''}"></label>
      </div>
    </details>
    <span class="small muted">Satiety tags</span>
    <div class="tag-row">${TAG_OPTIONS.map((t) =>
      `<button type="button" class="chip tappable ${tags.has(t.value) ? 'on' : ''}" data-tag="${t.value}">${t.label}</button>`).join('')}
      <button type="button" class="chip tappable ${f.vegan ? 'on' : ''}" data-tag="__vegan">Vegan</button>
    </div>
    <p class="small muted" data-slot="preview"></p>
    <button class="btn block" data-x="save">${isEdit ? 'Save changes' : 'Save product'}</button>`);

  let vegan = !!f.vegan;
  sheet.addEventListener('click', (e) => {
    const tagBtn = e.target.closest('[data-tag]');
    if (tagBtn) {
      const t = tagBtn.dataset.tag;
      if (t === '__vegan') vegan = !vegan;
      else if (tags.has(t)) tags.delete(t);
      else tags.add(t);
      tagBtn.classList.toggle('on');
    }
  });

  function collect() {
    const val = (n) => {
      const raw = $(`[name=${n}]`, sheet).value.trim();
      return raw === '' ? null : parseFloat(raw);
    };
    return {
      name: $('[name=name]', sheet).value.trim(),
      brand: $('[name=brand]', sheet).value.trim() || null,
      barcode: $('[name=barcode]', sheet).value.trim() || null,
      basis: $('[name=basis]', sheet).value,
      calories: val('calories') ?? 0,
      pack_g: val('pack_g'), pack_ml: val('pack_ml'),
      serving_g: val('serving_g'), items_per_pack: val('items_per_pack'),
      protein: val('protein'), carbs: val('carbs'), fat: val('fat'), fibre: val('fibre'),
      tags: [...tags], vegan,
    };
  }

  function preview() {
    const data = collect();
    const lbl = { per_100g: 'kcal per 100 g', per_100ml: 'kcal per 100 ml', per_pack: 'kcal per pack', per_item: 'kcal per item', per_serving: 'kcal per serving' };
    $('[data-slot=kcal-label]', sheet).textContent = `Calories (${lbl[data.basis] || 'kcal'})`;
    const bits = [];
    try {
      if (data.calories) {
        const w = foodNutrition(data, availableModes(data)[0]?.mode || 'grams',
          defaultAmount(data, availableModes(data)[0]?.mode || 'grams'));
        bits.push(`${availableModes(data)[0]?.label || ''}: ${Math.round(w.calories)} kcal`);
        if (data.basis !== 'per_100g' && data.pack_g && data.calories) {
          const per100 = foodNutrition(data, 'grams', 100);
          bits.push(`100 g ≈ ${Math.round(per100.calories)} kcal`);
        }
      }
    } catch { /* incomplete form */ }
    $('[data-slot=preview]', sheet).textContent = bits.join(' · ');
  }
  sheet.addEventListener('input', preview);
  preview();

  $('[data-x=save]', sheet).addEventListener('click', async () => {
    const data = collect();
    if (!data.name) { toast('Name is required', { bad: true }); return; }
    if (!(data.calories >= 0)) { toast('Calories required', { bad: true }); return; }

    if (isEdit) {
      let propagate = 'none';
      const { linked_entries: linked = 0 } =
        await api(`/api/catalog/foods/${food.id}/impact`).catch(() => ({}));
      if (linked > 0) {
        const choice = await propagateChoice(linked);
        if (choice === null) return;
        propagate = choice;
      }
      const res = await mutate('food', 'update', { id: food.id, propagate, ...data });
      if (res.status === 'applied') {
        const n = res.result?.recalculated_entries || 0;
        toast(n ? `Saved — ${n} past entries recalculated` : 'Product saved');
      }
    } else {
      const res = await mutate('food', 'create', data);
      if (res.status !== 'error') toast('Product saved to catalog');
      data.id = res.result?.id || res.op_id;
    }
    closeSheet(sheet);
    emit('data-changed');
    onSaved?.(data);
  });
}

async function propagateChoice(linked) {
  return new Promise((resolve) => {
    const sheet = openSheet(`
      <h2>Apply to history?</h2>
      <p class="muted">This item is linked to <b>${linked}</b> past diary
      ${linked === 1 ? 'entry' : 'entries'}. Old values are kept in the audit log either way.</p>
      <div style="display:flex;flex-direction:column;gap:10px;margin-top:12px">
        <button class="btn ghost block" data-v="none">Future entries only</button>
        <button class="btn block" data-v="past">Recalculate ${linked} past ${linked === 1 ? 'entry' : 'entries'}</button>
      </div>`);
    sheet.addEventListener('click', async (e) => {
      const b = e.target.closest('[data-v]');
      if (!b) return;
      const v = b.dataset.v;
      if (v === 'past') {
        const ok = await confirmSheet({
          title: 'Recalculate history?',
          body: `${linked} past ${linked === 1 ? 'entry' : 'entries'} will be updated to the new values. This cannot be undone in bulk, but every old value is preserved in the audit log.`,
          okLabel: 'Recalculate',
        });
        if (!ok) return;
      }
      closeSheet(sheet);
      resolve(v);
    });
    sheet.addEventListener('remove', () => resolve(null));
  });
}

// ------------------------------------------------------- quick / restaurant
export function quickForm({ source = 'quick', prefill = {}, onDone } = {}) {
  const isRestaurant = source === 'restaurant';
  const meal = prefill.meal || suggestMeal(S.settings || {}, nowMin(), S.today?.day_state);
  const tags = new Set(prefill.tags || []);
  const sheet = openSheet(`
    <h2>${isRestaurant ? 'Restaurant / takeaway' : 'Quick calories'}</h2>
    <label class="f"><span>What was it?</span>
      <input name="name" value="${esc(prefill.name || '')}" placeholder="${isRestaurant ? 'e.g. Burrito, medium' : 'e.g. Homemade soup'}"></label>
    <label class="f"><span>Calories</span>
      <input name="calories" type="text" inputmode="numeric" value="${prefill.calories ?? ''}" placeholder="kcal"></label>
    ${mealSelect(meal)}
    <span class="small muted">Accuracy</span>
    <div data-slot="accuracy" style="margin:6px 0 12px"></div>
    <details class="adv"><summary>Macros, note, tags</summary>
      <div class="frow">
        <label class="f"><span>Protein g</span><input name="protein" type="text" inputmode="decimal"></label>
        <label class="f"><span>Carbs g</span><input name="carbs" type="text" inputmode="decimal"></label>
      </div>
      <div class="frow">
        <label class="f"><span>Fat g</span><input name="fat" type="text" inputmode="decimal"></label>
        <label class="f"><span>Fibre g</span><input name="fibre" type="text" inputmode="decimal"></label>
      </div>
      <label class="f"><span>Note</span><input name="note" maxlength="500"></label>
      <div class="tag-row">${TAG_OPTIONS.map((t) =>
        `<button type="button" class="chip tappable ${tags.has(t.value) ? 'on' : ''}" data-tag="${t.value}">${t.label}</button>`).join('')}</div>
    </details>
    <details class="adv"><summary>Date &amp; time</summary>
      <div class="frow">
        <label class="f"><span>Date</span><input name="date" type="date" value="${prefill.date || todayStr()}"></label>
        <label class="f"><span>Time</span><input name="time" type="time" value="${prefill.time || nowHM()}"></label>
      </div>
    </details>
    <label class="f row" style="display:flex;align-items:center;gap:10px">
      <input name="saveMeal" type="checkbox" style="width:22px;min-height:22px;height:22px">
      <span style="margin:0">Save as reusable meal</span></label>
    <div data-slot="override"></div>
    <button class="btn block" data-x="log">Log it</button>`);

  let accuracy = prefill.accuracy || (isRestaurant ? 'good_estimate' : 'good_estimate');
  $('[data-slot=accuracy]', sheet).appendChild(
    segmented(ACCURACY_OPTIONS, accuracy, (v) => { accuracy = v; }));

  sheet.addEventListener('click', (e) => {
    const tagBtn = e.target.closest('[data-tag]');
    if (tagBtn) {
      const t = tagBtn.dataset.tag;
      if (tags.has(t)) tags.delete(t); else tags.add(t);
      tagBtn.classList.toggle('on');
    }
  });
  const refreshOverride = () => {
    $('[data-slot=override]', sheet).innerHTML = overrideChip(
      $('[name=meal]', sheet).value, [...tags], $('[name=date]', sheet).value);
  };
  sheet.addEventListener('input', refreshOverride);
  refreshOverride();

  $('[data-x=log]', sheet).addEventListener('click', async () => {
    const val = (n) => {
      const raw = $(`[name=${n}]`, sheet).value.trim();
      return raw === '' ? null : parseFloat(raw);
    };
    const name = $('[name=name]', sheet).value.trim();
    const calories = val('calories');
    if (!name || calories == null || Number.isNaN(calories)) {
      toast('Name and calories are required', { bad: true }); return;
    }
    const fields = {
      date: $('[name=date]', sheet).value, time: $('[name=time]', sheet).value,
      meal: $('[name=meal]', sheet).value, source,
      name, calories, accuracy,
      protein: val('protein'), carbs: val('carbs'), fat: val('fat'), fibre: val('fibre'),
      note: $('[name=note]', sheet).value.trim() || null,
      tags: [...tags],
    };
    if ($('[name=saveMeal]', sheet).checked) {
      await mutate('saved_meal', 'create', {
        name, calories, protein: fields.protein, carbs: fields.carbs,
        fat: fields.fat, fibre: fields.fibre, tags: [...tags].filter((t) => t !== 'low_energy'),
      });
      toast('Saved to your meals');
    }
    await submitDiary(fields);
    closeSheet(sheet);
    onDone?.();
  });
}

// ------------------------------------------------------------ saved meal
export function savedMealSheet(meal, { onDone } = {}) {
  const chosenMeal = suggestMeal(S.settings || {}, nowMin(), S.today?.day_state);
  const sheet = openSheet(`
    <h2>${esc(meal.name)}</h2>
    <p class="muted small">${Math.round(meal.calories)} kcal per serving
      ${meal.vegan ? ' · <span class="chip good">vegan</span>' : ''}</p>
    <label class="f"><span>Servings</span>
      <input name="amount" type="text" inputmode="decimal" value="1"></label>
    <div class="kcal-preview"><div class="v" data-slot="kcal">${Math.round(meal.calories)} kcal</div>
      <div class="m" data-slot="macros">${macroLine(meal)}</div></div>
    ${mealSelect(chosenMeal)}
    <div data-slot="override"></div>
    <button class="btn block" data-x="log">Log it</button>`);

  const update = () => {
    const a = parseFloat($('[name=amount]', sheet).value) || 0;
    const n = mealNutrition(meal, a);
    $('[data-slot=kcal]', sheet).textContent = `${Math.round(n.calories)} kcal`;
    $('[data-slot=macros]', sheet).textContent = macroLine(n);
    $('[data-slot=override]', sheet).innerHTML = overrideChip(
      $('[name=meal]', sheet).value, meal.tags, todayStr());
  };
  sheet.addEventListener('input', update);

  $('[data-x=log]', sheet).addEventListener('click', async () => {
    const a = parseFloat($('[name=amount]', sheet).value) || 1;
    const n = mealNutrition(meal, a);
    await submitDiary({
      date: todayStr(), time: nowHM(), meal: $('[name=meal]', sheet).value,
      source: 'saved_meal', ref_type: 'saved_meal', ref_id: meal.id,
      name: meal.name, amount_mode: 'servings', amount: a,
      calories: n.calories, protein: n.protein, carbs: n.carbs, fat: n.fat,
      fibre: n.fibre, tags: meal.tags || [],
    });
    closeSheet(sheet);
    onDone?.();
  });
}

export function savedMealForm({ meal, onSaved } = {}) {
  const f = meal || {};
  const isEdit = !!meal;
  const tags = new Set(f.tags || []);
  let vegan = !!f.vegan;
  const sheet = openSheet(`
    <h2>${isEdit ? 'Edit meal' : 'New saved meal'}</h2>
    <label class="f"><span>Name</span><input name="name" value="${esc(f.name || '')}"></label>
    <label class="f"><span>Calories per serving</span>
      <input name="calories" type="text" inputmode="numeric" value="${f.calories ?? ''}"></label>
    <details class="adv" ${f.protein != null ? 'open' : ''}><summary>Macros per serving</summary>
      <div class="frow">
        <label class="f"><span>Protein g</span><input name="protein" type="text" inputmode="decimal" value="${f.protein ?? ''}"></label>
        <label class="f"><span>Carbs g</span><input name="carbs" type="text" inputmode="decimal" value="${f.carbs ?? ''}"></label>
      </div>
      <div class="frow">
        <label class="f"><span>Fat g</span><input name="fat" type="text" inputmode="decimal" value="${f.fat ?? ''}"></label>
        <label class="f"><span>Fibre g</span><input name="fibre" type="text" inputmode="decimal" value="${f.fibre ?? ''}"></label>
      </div>
    </details>
    <div class="tag-row">${TAG_OPTIONS.filter((t) => t.value !== 'low_energy').map((t) =>
      `<button type="button" class="chip tappable ${tags.has(t.value) ? 'on' : ''}" data-tag="${t.value}">${t.label}</button>`).join('')}
      <button type="button" class="chip tappable ${vegan ? 'on' : ''}" data-tag="__vegan">Vegan</button></div>
    <div class="frow">
      ${isEdit ? '<button class="btn danger block" data-x="delete">Delete</button>' : ''}
      <button class="btn block" data-x="save">Save</button>
    </div>`);

  sheet.addEventListener('click', async (e) => {
    const tagBtn = e.target.closest('[data-tag]');
    if (tagBtn) {
      const t = tagBtn.dataset.tag;
      if (t === '__vegan') vegan = !vegan;
      else if (tags.has(t)) tags.delete(t); else tags.add(t);
      tagBtn.classList.toggle('on');
      return;
    }
    const x = e.target.closest('[data-x]');
    if (!x) return;
    if (x.dataset.x === 'delete') {
      if (!(await confirmSheet({ title: 'Delete meal?', body: 'Past diary entries keep their values. The meal is soft-deleted and recoverable from the audit log.', okLabel: 'Delete', danger: true }))) return;
      await mutate('saved_meal', 'delete', { id: meal.id });
      toast('Meal deleted');
      closeSheet(sheet); emit('data-changed'); onSaved?.(); return;
    }
    const val = (n) => {
      const raw = $(`[name=${n}]`, sheet).value.trim();
      return raw === '' ? null : parseFloat(raw);
    };
    const data = {
      name: $('[name=name]', sheet).value.trim(), calories: val('calories') ?? 0,
      protein: val('protein'), carbs: val('carbs'), fat: val('fat'), fibre: val('fibre'),
      tags: [...tags], vegan,
    };
    if (!data.name) { toast('Name required', { bad: true }); return; }
    if (isEdit) {
      let propagate = 'none';
      const { linked_entries: linked = 0 } =
        await api(`/api/catalog/meals/${meal.id}/impact`).catch(() => ({}));
      if (linked > 0) {
        const choice = await propagateChoice(linked);
        if (choice === null) return;
        propagate = choice;
      }
      await mutate('saved_meal', 'update', { id: meal.id, propagate, ...data });
    } else {
      await mutate('saved_meal', 'create', data);
    }
    toast('Meal saved');
    closeSheet(sheet); emit('data-changed'); onSaved?.(data);
  });
}

// --------------------------------------------------------------- recipes
export function recipePortionSheet(recipe, { onDone } = {}) {
  const totals = recipeTotals(recipe);
  const modes = [];
  if (totals.per_portion) modes.push({ value: 'portion', label: 'Portions' });
  if (totals.per_100g) modes.push({ value: 'grams', label: 'Grams' });
  modes.push({ value: 'fraction', label: 'Fraction of batch' });
  let mode = modes[0].value;
  const chosenMeal = suggestMeal(S.settings || {}, nowMin(), S.today?.day_state);

  const sheet = openSheet(`
    <h2>${esc(recipe.name)}</h2>
    <p class="muted small">${Math.round(totals.total.calories)} kcal total
      ${totals.per_portion ? ` · ${Math.round(totals.per_portion.calories)} kcal/portion` : ''}
      ${totals.per_100g ? ` · ${Math.round(totals.per_100g.calories)} kcal/100g` : ''}</p>
    <div data-slot="modes" style="margin-bottom:10px"></div>
    <label class="f"><span data-slot="amount-label">Amount</span>
      <input name="amount" type="text" inputmode="decimal" value="1"></label>
    <div class="kcal-preview"><div class="v" data-slot="kcal">–</div>
      <div class="m" data-slot="macros"></div></div>
    ${mealSelect(chosenMeal)}
    <div data-slot="override"></div>
    <button class="btn block" data-x="log">Log it</button>`);

  $('[data-slot=modes]', sheet).appendChild(segmented(modes, mode, (v) => {
    mode = v;
    $('[name=amount]', sheet).value = mode === 'grams' ? 150 : mode === 'fraction' ? 0.25 : 1;
    update();
  }));
  const update = () => {
    const a = parseFloat($('[name=amount]', sheet).value) || 0;
    let n;
    try { n = recipeNutrition(recipe, mode, a); } catch { n = { calories: NaN }; }
    $('[data-slot=kcal]', sheet).textContent =
      Number.isNaN(n.calories) ? '—' : `${Math.round(n.calories)} kcal`;
    $('[data-slot=macros]', sheet).textContent = Number.isNaN(n.calories) ? '' : macroLine(n);
    $('[data-slot=amount-label]', sheet).textContent =
      mode === 'grams' ? 'Amount (g cooked)' : mode === 'fraction' ? 'Fraction of whole batch' : 'Portions';
    $('[data-slot=override]', sheet).innerHTML = overrideChip(
      $('[name=meal]', sheet).value, recipe.tags, todayStr());
  };
  sheet.addEventListener('input', update);
  update();

  $('[data-x=log]', sheet).addEventListener('click', async () => {
    const a = parseFloat($('[name=amount]', sheet).value) || 1;
    let n;
    try { n = recipeNutrition(recipe, mode, a); } catch { toast('Enter a valid amount', { bad: true }); return; }
    await submitDiary({
      date: todayStr(), time: nowHM(), meal: $('[name=meal]', sheet).value,
      source: 'recipe', ref_type: 'recipe', ref_id: recipe.id, name: recipe.name,
      amount_mode: mode, amount: a, calories: n.calories,
      protein: n.protein, carbs: n.carbs, fat: n.fat, fibre: n.fibre,
      tags: recipe.tags || [],
    });
    closeSheet(sheet);
    onDone?.();
  });
}

export function recipeForm({ recipe, onSaved } = {}) {
  const f = recipe || { ingredients: [{}] };
  const isEdit = !!recipe;
  const sheet = openSheet(`
    <h2>${isEdit ? 'Edit recipe' : 'New recipe'}</h2>
    <label class="f"><span>Name</span><input name="name" value="${esc(f.name || '')}"></label>
    <h3>Ingredients</h3>
    <div data-slot="ingredients"></div>
    <button class="btn ghost small" data-x="add-ing" type="button">+ Add ingredient</button>
    <div class="frow" style="margin-top:12px">
      <label class="f"><span>Cooked yield (g)</span>
        <input name="cooked_yield_g" type="text" inputmode="decimal" value="${f.cooked_yield_g ?? ''}"></label>
      <label class="f"><span>Portions</span>
        <input name="portions" type="text" inputmode="decimal" value="${f.portions ?? ''}"></label>
    </div>
    <div class="card flat" data-slot="totals"></div>
    <div class="frow">
      ${isEdit ? '<button class="btn danger block" data-x="delete">Delete</button>' : ''}
      <button class="btn block" data-x="save">Save recipe</button>
    </div>`);

  const ingWrap = $('[data-slot=ingredients]', sheet);
  const addRow = (ing = {}) => {
    const row = h(`<div class="card flat" style="margin-bottom:8px">
      <label class="f"><span>Ingredient</span><input data-i="name" value="${esc(ing.name || '')}"></label>
      <div class="frow">
        <label class="f"><span>Amount (g or ml)</span>
          <input data-i="amount" type="text" inputmode="decimal" value="${ing.amount_g ?? ing.amount_ml ?? ''}"></label>
        <label class="f"><span>Calories</span>
          <input data-i="calories" type="text" inputmode="decimal" value="${ing.calories ?? ''}"></label>
      </div>
      <details class="adv"><summary>Macros</summary>
        <div class="frow">
          <label class="f"><span>P</span><input data-i="protein" type="text" inputmode="decimal" value="${ing.protein ?? ''}"></label>
          <label class="f"><span>C</span><input data-i="carbs" type="text" inputmode="decimal" value="${ing.carbs ?? ''}"></label>
          <label class="f"><span>F</span><input data-i="fat" type="text" inputmode="decimal" value="${ing.fat ?? ''}"></label>
          <label class="f"><span>Fb</span><input data-i="fibre" type="text" inputmode="decimal" value="${ing.fibre ?? ''}"></label>
        </div>
      </details>
      <button type="button" class="btn danger small" data-x="rm">Remove</button>
    </div>`);
    $('[data-x=rm]', row).addEventListener('click', () => { row.remove(); totals(); });
    ingWrap.appendChild(row);
  };
  (f.ingredients?.length ? f.ingredients : [{}]).forEach(addRow);

  const collect = () => {
    const ingredients = $$('[data-slot=ingredients] > .card', sheet).map((row) => {
      const g = (n) => {
        const raw = $(`[data-i=${n}]`, row).value.trim();
        return raw === '' ? null : parseFloat(raw);
      };
      return {
        name: $('[data-i=name]', row).value.trim(),
        amount_g: g('amount'), calories: g('calories') ?? 0,
        protein: g('protein'), carbs: g('carbs'), fat: g('fat'), fibre: g('fibre'),
      };
    }).filter((i) => i.name);
    const num = (n) => {
      const raw = $(`[name=${n}]`, sheet).value.trim();
      return raw === '' ? null : parseFloat(raw);
    };
    return {
      name: $('[name=name]', sheet).value.trim(),
      ingredients,
      cooked_yield_g: num('cooked_yield_g'),
      portions: num('portions'),
      vegan: f.vegan || false, tags: f.tags || [],
    };
  };

  const totals = () => {
    const data = collect();
    const t = recipeTotals(data);
    $('[data-slot=totals]', sheet).innerHTML = `
      <b>${Math.round(t.total.calories)} kcal total</b>
      <span class="muted small"> · ${t.per_100g ? `${Math.round(t.per_100g.calories)} kcal/100g · ` : ''}
      ${t.per_portion ? `${Math.round(t.per_portion.calories)} kcal/portion` : 'set portions for per-portion'}</span>`;
  };
  sheet.addEventListener('input', totals);
  totals();

  sheet.addEventListener('click', async (e) => {
    const x = e.target.closest('[data-x]');
    if (!x) return;
    if (x.dataset.x === 'add-ing') { addRow(); return; }
    if (x.dataset.x === 'rm') return; // handled per-row
    if (x.dataset.x === 'delete') {
      if (!(await confirmSheet({ title: 'Delete recipe?', body: 'Past entries keep their values (soft delete).', okLabel: 'Delete', danger: true }))) return;
      await mutate('recipe', 'delete', { id: recipe.id });
      closeSheet(sheet); emit('data-changed'); onSaved?.(); return;
    }
    if (x.dataset.x !== 'save') return;
    const data = collect();
    if (!data.name || !data.ingredients.length) {
      toast('Name and at least one ingredient required', { bad: true }); return;
    }
    if (isEdit) {
      let propagate = 'none';
      const { linked_entries: linked = 0 } =
        await api(`/api/catalog/recipes/${recipe.id}/impact`).catch(() => ({}));
      if (linked > 0) {
        const choice = await propagateChoice(linked);
        if (choice === null) return;
        propagate = choice;
      }
      await mutate('recipe', 'update', { id: recipe.id, propagate, ...data });
    } else {
      await mutate('recipe', 'create', data);
    }
    toast('Recipe saved');
    closeSheet(sheet); emit('data-changed'); onSaved?.(data);
  });
}

// ---------------------------------------------------------- entry editor
export async function entryEditSheet(entry, { onDone } = {}) {
  let ref = null;
  if (entry.ref_type === 'food' && entry.ref_id && entry.amount_mode && entry.amount_mode !== 'direct') {
    ref = await api(`/api/catalog/foods/${entry.ref_id}`).catch(() => null);
  }
  const linked = !!ref;
  const sheet = openSheet(`
    <h2>${esc(entry.name)}</h2>
    <p class="muted small">${entry.source.replace(/_/g, ' ')}${entry.brand ? ` · ${esc(entry.brand)}` : ''}
      ${entry.override ? `· <span class="chip warn">${entry.override.replace(/_/g, ' ')}</span>` : ''}</p>
    ${linked ? `
      <div class="frow">
        <label class="f"><span>Mode</span><select name="amount_mode">${availableModes(ref).map((m) =>
          `<option value="${m.mode}" ${entry.amount_mode === m.mode ? 'selected' : ''}>${m.label}</option>`).join('')}
        </select></label>
        <label class="f"><span>Amount</span>
          <input name="amount" type="text" inputmode="decimal" value="${entry.amount ?? 1}"></label>
      </div>
      <p class="small muted" data-slot="calc"></p>` : `
      <label class="f"><span>Calories</span>
        <input name="calories" type="text" inputmode="numeric" value="${Math.round(entry.calories)}"></label>
      <details class="adv"><summary>Macros</summary>
        <div class="frow">
          <label class="f"><span>Protein g</span><input name="protein" type="text" inputmode="decimal" value="${entry.protein ?? ''}"></label>
          <label class="f"><span>Carbs g</span><input name="carbs" type="text" inputmode="decimal" value="${entry.carbs ?? ''}"></label>
        </div>
        <div class="frow">
          <label class="f"><span>Fat g</span><input name="fat" type="text" inputmode="decimal" value="${entry.fat ?? ''}"></label>
          <label class="f"><span>Fibre g</span><input name="fibre" type="text" inputmode="decimal" value="${entry.fibre ?? ''}"></label>
        </div>
      </details>`}
    ${mealSelect(entry.meal)}
    <div class="frow">
      <label class="f"><span>Date</span><input name="date" type="date" value="${entry.date}"></label>
      <label class="f"><span>Time</span><input name="time" type="time" value="${entry.time}"></label>
    </div>
    <label class="f"><span>Accuracy</span>
      <select name="accuracy">
        <option value="">—</option>
        ${ACCURACY_OPTIONS.map((a) => `<option value="${a.value}" ${entry.accuracy === a.value ? 'selected' : ''}>${a.label}</option>`).join('')}
      </select></label>
    <label class="f"><span>Note</span><input name="note" value="${esc(entry.note || '')}" maxlength="500"></label>
    <div class="frow" style="margin-bottom:10px">
      <button class="btn ghost block" data-x="fav">${entry.favourite ? '★ Unfavourite' : '☆ Favourite'}</button>
      <button class="btn ghost block" data-x="dup">Duplicate to today</button>
    </div>
    <div class="frow">
      <button class="btn danger block" data-x="del">Delete</button>
      <button class="btn block" data-x="save">Save</button>
    </div>`);

  if (linked) {
    const calcLine = () => {
      const mode = $('[name=amount_mode]', sheet).value;
      const a = parseFloat($('[name=amount]', sheet).value) || 0;
      try {
        const n = foodNutrition(ref, mode, a);
        $('[data-slot=calc]', sheet).textContent = `= ${Math.round(n.calories)} kcal · ${macroLine(n)}`;
      } catch { $('[data-slot=calc]', sheet).textContent = ''; }
    };
    sheet.addEventListener('input', calcLine);
    calcLine();
  }

  sheet.addEventListener('click', async (e) => {
    const x = e.target.closest('[data-x]');
    if (!x) return;
    const patch = { id: entry.id };
    if (x.dataset.x === 'fav') {
      await mutate('diary', 'update', { id: entry.id, favourite: !entry.favourite });
      toast(entry.favourite ? 'Removed from favourites' : 'Added to favourites');
      closeSheet(sheet); emit('data-changed'); onDone?.(); return;
    }
    if (x.dataset.x === 'dup') {
      const copy = { ...entry };
      delete copy.id; delete copy.created_at; delete copy.updated_at; delete copy.deleted_at;
      copy.date = todayStr(); copy.time = nowHM(); copy.source = 'copy';
      copy.favourite = !!copy.favourite; copy.override = null;
      copy.meal = suggestMeal(S.settings || {}, nowMin(), S.today?.day_state);
      await submitDiary(copy);
      closeSheet(sheet); onDone?.(); return;
    }
    if (x.dataset.x === 'del') {
      const ok = await confirmSheet({
        title: 'Delete entry?',
        body: 'Soft delete — recoverable via Undo or the audit log.',
        okLabel: 'Delete', danger: true,
      });
      if (!ok) return;
      await mutate('diary', 'delete', { id: entry.id });
      closeSheet(sheet); emit('data-changed');
      toast('Entry deleted', {
        action: 'Undo',
        onAction: async () => { await mutate('diary', 'undelete', { id: entry.id }); emit('data-changed'); },
      });
      onDone?.(); return;
    }
    if (x.dataset.x !== 'save') return;
    const val = (n) => {
      const node = $(`[name=${n}]`, sheet);
      if (!node) return undefined;
      const raw = node.value.trim();
      return raw === '' ? null : parseFloat(raw);
    };
    patch.date = $('[name=date]', sheet).value;
    patch.time = $('[name=time]', sheet).value;
    patch.meal = $('[name=meal]', sheet).value;
    patch.accuracy = $('[name=accuracy]', sheet).value || null;
    patch.note = $('[name=note]', sheet).value.trim() || null;
    if (linked) {
      patch.amount_mode = $('[name=amount_mode]', sheet).value;
      patch.amount = parseFloat($('[name=amount]', sheet).value) || entry.amount;
    } else {
      patch.calories = val('calories') ?? entry.calories;
      for (const m of MACROS) {
        const v = val(m);
        if (v !== undefined) patch[m] = v;
      }
    }
    Object.keys(patch).forEach((k) => { if (patch[k] === null) delete patch[k]; });
    const res = await mutate('diary', 'update', patch);
    if (res.status !== 'error') toast('Entry updated');
    closeSheet(sheet); emit('data-changed'); onDone?.();
  });
}

// --------------------------------------------------------- copy previous
export async function copyPreviousSheet({ onDone } = {}) {
  let data;
  try { data = await api('/api/diary/recent'); } catch { data = { favourites: [], recent: [] }; }
  const row = (e) => `
    <div class="entry" data-copy='${esc(JSON.stringify({
      name: e.name, calories: e.calories, protein: e.protein, carbs: e.carbs,
      fat: e.fat, fibre: e.fibre, tags: e.tags, accuracy: e.accuracy,
      ref_type: e.ref_type, ref_id: e.ref_id, amount_mode: e.amount_mode,
      amount: e.amount, brand: e.brand,
    }))}'>
      <div class="main"><div class="name">${e.favourite ? '★ ' : ''}${esc(e.name)}</div>
        <div class="sub">${esc(e.meal)} · ${e.date}</div></div>
      <div class="kcal">${Math.round(e.calories)}</div>
    </div>`;
  const sheet = openSheet(`
    <h2>Copy previous</h2>
    ${data.favourites.length ? `<h3>Favourites</h3><div class="pick-list">${data.favourites.map(row).join('')}</div>` : ''}
    <h3>Recent</h3>
    <div class="pick-list">${data.recent.length ? data.recent.map(row).join('') : '<p class="muted">Nothing logged yet.</p>'}</div>`);
  sheet.addEventListener('click', async (e) => {
    const item = e.target.closest('[data-copy]');
    if (!item) return;
    const src = JSON.parse(item.dataset.copy);
    await submitDiary({
      ...src,
      date: todayStr(), time: nowHM(),
      meal: suggestMeal(S.settings || {}, nowMin(), S.today?.day_state),
      source: 'copy',
    });
    closeSheet(sheet);
    onDone?.();
  });
}

// ------------------------------------------------------------- body logs
export function bodyLogSheet(kind, { latest, onDone } = {}) {
  const cfg = {
    weight: { title: 'Log weight', unit: 'kg', field: 'kg', step: '0.1', min: 25, max: 350 },
    waist: { title: 'Log waist', unit: 'cm', field: 'cm', step: '0.5', min: 40, max: 250 },
    steps: { title: 'Log steps', unit: 'steps', field: 'steps', step: '1', min: 0, max: 200000 },
  }[kind];
  const sheet = openSheet(`
    <h2>${cfg.title}</h2>
    <div class="frow">
      <label class="f"><span>Date</span><input name="date" type="date" value="${todayStr()}"></label>
      <label class="f"><span>${cfg.unit}</span>
        <input name="value" type="text" inputmode="decimal" value="${latest ?? ''}" placeholder="${cfg.unit}"></label>
    </div>
    ${kind === 'waist' ? '<p class="small muted">Weekly is plenty — same time of day, relaxed tape.</p>' : ''}
    <button class="btn block" data-x="save">Save</button>`);
  $('[data-x=save]', sheet).addEventListener('click', async () => {
    const v = parseFloat($('[name=value]', sheet).value);
    if (Number.isNaN(v) || v < cfg.min || v > cfg.max) {
      toast(`Enter a value between ${cfg.min} and ${cfg.max}`, { bad: true }); return;
    }
    const payload = { date: $('[name=date]', sheet).value };
    payload[cfg.field] = kind === 'steps' ? Math.round(v) : v;
    const res = await mutate(kind, 'log', payload);
    if (res.status !== 'error') toast(`${cfg.title.replace('Log ', '')} saved`.replace(/^\w/, (c) => c.toUpperCase()));
    closeSheet(sheet); emit('data-changed'); onDone?.();
  });
}
