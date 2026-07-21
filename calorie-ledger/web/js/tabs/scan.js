// Scan tab: camera barcode scan (local FoodCatalog only) with manual-entry
// fallback. Found -> amount sheet. New -> create product, then log it.

import { api } from '../api.js';
import { Scanner, scannerSupported } from '../scanner.js';
import { amountSheet, productForm } from '../sheets.js';
import { $, esc, h, toast } from '../util.js';

let scanner = null;

export async function render(el) {
  el.innerHTML = `
    <h2>Scan a barcode</h2>
    ${scannerSupported() ? `
      <div class="scan-stage"><video muted playsinline></video><div class="scan-frame"></div></div>
      <div class="row" style="justify-content:center;margin-bottom:14px">
        <button class="btn ghost" data-x="toggle">Start camera</button>
      </div>` : `
      <div class="card"><p class="muted" style="margin:0">This browser has no built-in barcode
      detector (iOS 17+ required). Type the number instead — same flow, same catalog.</p></div>`}
    <div class="card">
      <h3>Barcode number</h3>
      <form data-x="manual" class="row">
        <input name="code" inputmode="numeric" autocomplete="off" placeholder="e.g. 5000159484695">
        <button class="btn" style="flex-shrink:0">Find</button>
      </form>
      <p class="small muted" style="margin:8px 0 0">Lookups stay on your server — nothing is sent
      to any external food database.</p>
    </div>
    <div data-slot="result"></div>`;

  const video = $('video', el);
  const toggle = $('[data-x=toggle]', el);
  if (toggle) {
    toggle.addEventListener('click', async () => {
      if (scanner?.running) { stopScanner(); toggle.textContent = 'Start camera'; return; }
      try {
        scanner = new Scanner(video, (code) => {
          toggle.textContent = 'Start camera';
          handleCode(el, code);
        });
        await scanner.start();
        toggle.textContent = 'Stop camera';
      } catch (err) {
        stopScanner();
        toast(err?.name === 'NotAllowedError'
          ? 'Camera permission denied — use manual entry'
          : 'Camera unavailable — use manual entry', { bad: true });
      }
    });
  }

  $('[data-x=manual]', el).addEventListener('submit', (e) => {
    e.preventDefault();
    const code = $('[name=code]', el).value.trim();
    if (code.length < 4) { toast('Enter the full barcode', { bad: true }); return; }
    handleCode(el, code);
  });
}

async function handleCode(el, code) {
  const slot = $('[data-slot=result]', el);
  slot.innerHTML = `<div class="card"><p class="muted">Looking up ${esc(code)}…</p></div>`;
  let res;
  try {
    res = await api(`/api/catalog/foods?barcode=${encodeURIComponent(code)}`);
  } catch {
    slot.innerHTML = `<div class="card"><p class="muted">Offline — can't search the catalog.
      Use Quick calories on the Log tab, or retry when connected.</p></div>`;
    return;
  }
  if (res.matched) {
    const food = res.foods[0];
    slot.innerHTML = `<div class="card"><b>${esc(food.name)}</b>
      <span class="muted small">${esc(food.brand || '')}</span></div>`;
    amountSheet(food, { source: 'barcode_product', onDone: () => { slot.innerHTML = ''; } });
  } else {
    slot.innerHTML = `<div class="card"><b>Not in your catalog yet</b>
      <p class="muted small" style="margin:6px 0 10px">Add it once from the label — it's yours
      forever after that.</p>
      <button class="btn block" data-x="create">Create product ${esc(code)}</button></div>`;
    $('[data-x=create]', slot).addEventListener('click', () => {
      productForm({
        barcode: code,
        onSaved: async () => {
          // Straight into logging the thing you just scanned.
          const again = await api(`/api/catalog/foods?barcode=${encodeURIComponent(code)}`).catch(() => null);
          if (again?.matched) amountSheet(again.foods[0], { source: 'barcode_product' });
          slot.innerHTML = '';
        },
      });
    });
  }
}

function stopScanner() {
  if (scanner) { scanner.stop(); scanner = null; }
}

export function onLeave() {
  stopScanner();
}
