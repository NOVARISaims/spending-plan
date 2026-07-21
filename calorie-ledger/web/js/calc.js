// Client mirror of server/app/calc.py — live previews only; the server
// recomputes on save so stored numbers are always server-derived.

export const MACROS = ['protein', 'carbs', 'fat', 'fibre'];

function need(food, field) {
  const v = Number(food[field]);
  if (!v) throw new Error(`needs ${field}`);
  return v;
}

export function basisFactor(food, mode, amount) {
  const basis = food.basis;
  const a = amount == null ? 1 : Number(amount);
  if (Number.isNaN(a) || a < 0) throw new Error('bad amount');

  if (basis === 'per_100g' || basis === 'per_100ml') {
    const unit = basis === 'per_100g' ? 'pack_g' : 'pack_ml';
    if (mode === 'grams' || mode === 'ml') return a / 100;
    if (mode === 'whole_pack') return need(food, unit) / 100;
    if (mode === 'fraction') return (need(food, unit) * a) / 100;
    if (mode === 'servings') return (need(food, 'serving_g') * a) / 100;
    if (mode === 'items') {
      return ((need(food, unit) / need(food, 'items_per_pack')) * a) / 100;
    }
  } else if (basis === 'per_pack') {
    if (mode === 'whole_pack') return 1;
    if (mode === 'fraction') return a;
    if (mode === 'grams') return a / need(food, 'pack_g');
    if (mode === 'ml') return a / need(food, 'pack_ml');
    if (mode === 'items') return a / need(food, 'items_per_pack');
    if (mode === 'servings') return (need(food, 'serving_g') * a) / need(food, 'pack_g');
  } else if (basis === 'per_item') {
    if (mode === 'items') return a;
    if (mode === 'whole_pack') return need(food, 'items_per_pack');
    if (mode === 'fraction') return need(food, 'items_per_pack') * a;
    if (mode === 'grams') return a / (need(food, 'pack_g') / need(food, 'items_per_pack'));
  } else if (basis === 'per_serving') {
    if (mode === 'servings') return a;
    if (mode === 'grams') return a / need(food, 'serving_g');
    if (mode === 'whole_pack') return need(food, 'pack_g') / need(food, 'serving_g');
    if (mode === 'fraction') return (need(food, 'pack_g') / need(food, 'serving_g')) * a;
  }
  throw new Error(`mode ${mode} invalid for ${basis}`);
}

export function foodNutrition(food, mode, amount) {
  const f = basisFactor(food, mode, amount);
  const out = { calories: round1(food.calories * f) };
  for (const m of MACROS) out[m] = food[m] == null ? null : round1(food[m] * f);
  return out;
}

// Which amount modes make sense for this product, given the fields it has.
export function availableModes(food) {
  const has = (k) => Number(food[k]) > 0;
  const modes = [];
  const push = (mode, label) => modes.push({ mode, label });
  switch (food.basis) {
    case 'per_100g':
      if (has('pack_g')) push('whole_pack', 'Whole pack');
      push('grams', 'Grams');
      if (has('pack_g')) push('fraction', 'Fraction of pack');
      if (has('serving_g')) push('servings', 'Servings');
      if (has('pack_g') && has('items_per_pack')) push('items', 'Items');
      break;
    case 'per_100ml':
      if (has('pack_ml')) push('whole_pack', 'Whole pack');
      push('ml', 'Millilitres');
      if (has('pack_ml')) push('fraction', 'Fraction of pack');
      if (has('pack_ml') && has('items_per_pack')) push('items', 'Items');
      break;
    case 'per_pack':
      push('whole_pack', 'Whole pack');
      push('fraction', 'Fraction of pack');
      if (has('pack_g')) push('grams', 'Grams');
      if (has('pack_ml')) push('ml', 'Millilitres');
      if (has('items_per_pack')) push('items', 'Items');
      if (has('pack_g') && has('serving_g')) push('servings', 'Servings');
      break;
    case 'per_item':
      push('items', 'Items');
      if (has('items_per_pack')) push('whole_pack', 'Whole pack');
      if (has('items_per_pack') && has('pack_g')) push('grams', 'Grams');
      break;
    case 'per_serving':
      push('servings', 'Servings');
      if (has('serving_g')) push('grams', 'Grams');
      if (has('pack_g') && has('serving_g')) push('whole_pack', 'Whole pack');
      break;
  }
  return modes;
}

export function recipeTotals(recipe) {
  const total = { calories: 0 };
  const seen = {};
  let raw = 0;
  for (const m of MACROS) { total[m] = 0; seen[m] = false; }
  for (const ing of recipe.ingredients || []) {
    total.calories += Number(ing.calories || 0);
    raw += Number(ing.amount_g || ing.amount_ml || 0);
    for (const m of MACROS) {
      if (ing[m] != null && ing[m] !== '') { total[m] += Number(ing[m]); seen[m] = true; }
    }
  }
  for (const m of MACROS) total[m] = seen[m] ? round1(total[m]) : null;
  total.calories = round1(total.calories);
  const out = { total, raw_weight_g: round1(raw), per_100g: null, per_portion: null };
  if (Number(recipe.cooked_yield_g) > 0) out.per_100g = scaled(total, 100 / recipe.cooked_yield_g);
  if (Number(recipe.portions) > 0) out.per_portion = scaled(total, 1 / recipe.portions);
  return out;
}

export function recipeNutrition(recipe, mode, amount) {
  const t = recipeTotals(recipe);
  const a = amount == null ? 1 : Number(amount);
  if (mode === 'portion') {
    if (!t.per_portion) throw new Error('recipe has no portion count');
    return scaled(t.per_portion, a);
  }
  if (mode === 'grams') {
    if (!t.per_100g) throw new Error('recipe has no cooked yield');
    return scaled(t.per_100g, a / 100);
  }
  if (mode === 'fraction') return scaled(t.total, a);
  throw new Error(`mode ${mode} invalid for recipe`);
}

export function mealNutrition(meal, servings) {
  return scaled({ calories: meal.calories, ...pick(meal) }, servings == null ? 1 : Number(servings));
}

function pick(o) {
  const out = {};
  for (const m of MACROS) out[m] = o[m];
  return out;
}

function scaled(values, f) {
  const out = { calories: round1(values.calories * f) };
  for (const m of MACROS) out[m] = values[m] == null ? null : round1(values[m] * f);
  return out;
}

const round1 = (n) => Math.round(Number(n) * 10) / 10;
