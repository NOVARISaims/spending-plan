
/* Minimal local-only app with client-side encryption.
 * Data model:
 *  state = {
 *    version: 1,
 *    workbookName: "",
 *    sheets: {
 *      [sheetName]: {
 *        columns: [colA, colB, ...],
 *        rows: [{colA: value, colB: value, ...}, ...],
 *        mapping: { date: "Date", eod: "Balance", allow: "Allowance", comment: "Comment" }
 *      }
 *    }
 *  }
 *
 * Encrypted and stored in localStorage under key 'sp-plan' using AES-GCM with a key
 * derived from the passcode. Salt and iv stored alongside ciphertext.
 */

const els = {
  lock: document.getElementById('lock'),
  pin: document.getElementById('pin'),
  btnUnlock: document.getElementById('btn-unlock'),
  hint: document.getElementById('lock-hint'),
  fileBtn: document.getElementById('btn-import'),
  fileInput: document.getElementById('file-input'),
  settingsBtn: document.getElementById('btn-settings'),
  settingsDlg: document.getElementById('settings'),
  btnDelete: document.getElementById('btn-delete-data'),
  btnChangePin: document.getElementById('btn-change-pin'),
  monthSelect: document.getElementById('month-select'),
  mappingSec: document.getElementById('mapping'),
  mapDate: document.getElementById('map-date'),
  mapEod: document.getElementById('map-eod'),
  mapAllow: document.getElementById('map-allow'),
  mapComment: document.getElementById('map-comment'),
  btnSaveMapping: document.getElementById('btn-save-mapping'),
  tableBody: document.getElementById('data-body'),
  table: document.getElementById('data-table'),
  title: document.getElementById('sheet-title'),
  summary: document.getElementById('summary'),
  btnExport: document.getElementById('btn-export')
};

// ---------- Crypto helpers ----------
const STORAGE_KEY = 'sp-plan';
const SALT_KEY = 'sp-salt';
const NONCE_KEY = 'sp-nonce';
let gKey = null; // CryptoKey after unlock

async function deriveKey(pass) {
  const enc = new TextEncoder();
  let salt = localStorage.getItem(SALT_KEY);
  if (!salt) {
    salt = crypto.getRandomValues(new Uint8Array(16));
    localStorage.setItem(SALT_KEY, btoa(String.fromCharCode(...salt)));
  } else {
    salt = new Uint8Array(atob(salt).split('').map(c=>c.charCodeAt(0)));
  }
  const baseKey = await crypto.subtle.importKey('raw', enc.encode(pass), {name:'PBKDF2'}, false, ['deriveKey']);
  return crypto.subtle.deriveKey(
    {name:'PBKDF2', salt, iterations: 200000, hash:'SHA-256'},
    baseKey,
    {name:'AES-GCM', length: 256},
    false,
    ['encrypt','decrypt']
  );
}

async function encryptState(obj) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const data = new TextEncoder().encode(JSON.stringify(obj));
  const ct = await crypto.subtle.encrypt({name:'AES-GCM', iv}, gKey, data);
  localStorage.setItem(NONCE_KEY, btoa(String.fromCharCode(...iv)));
  localStorage.setItem(STORAGE_KEY, btoa(String.fromCharCode(...new Uint8Array(ct))));
}

async function decryptState() {
  const ivStr = localStorage.getItem(NONCE_KEY);
  const ctStr = localStorage.getItem(STORAGE_KEY);
  if (!ivStr || !ctStr) return null;
  const iv = new Uint8Array(atob(ivStr).split('').map(c=>c.charCodeAt(0)));
  const ct = new Uint8Array(atob(ctStr).split('').map(c=>c.charCodeAt(0)));
  const pt = await crypto.subtle.decrypt({name:'AES-GCM', iv}, gKey, ct);
  return JSON.parse(new TextDecoder().decode(pt));
}

// ---------- App state ----------
let state = null; // decrypted

function newState() {
  return { version: 1, workbookName: "", sheets: {} };
}

// ---------- UI Logic ----------
function setLocked(locked) {
  els.lock.style.display = locked ? 'grid' : 'none';
}

function renderMonths() {
  const names = Object.keys(state.sheets);
  els.monthSelect.innerHTML = names.map(n => `<option>${n}</option>`).join('');
  if (names.length) {
    els.monthSelect.value = names[0];
    renderSheet(names[0]);
  } else {
    els.title.textContent = 'No sheet loaded';
    els.tableBody.innerHTML = '';
  }
}

function ensureMapping(sheet) {
  const s = state.sheets[sheet];
  const cols = s.columns;
  const map = s.mapping || {};
  const selects = [els.mapDate, els.mapEod, els.mapAllow, els.mapComment];
  [els.mapDate, els.mapEod, els.mapAllow, els.mapComment].forEach(sel => {
    sel.innerHTML = '<option value="">-- Select --</option>' + cols.map(c => `<option value="${c}">${c}</option>`).join('');
  });
  if (map.date) els.mapDate.value = map.date;
  if (map.eod) els.mapEod.value = map.eod;
  if (map.allow) els.mapAllow.value = map.allow;
  if (map.comment) els.mapComment.value = map.comment;
  els.mappingSec.classList.remove('hidden');
}

function renderSheet(name) {
  const s = state.sheets[name];
  els.title.textContent = name;
  ensureMapping(name);

  // build summary pills if possible
  els.summary.innerHTML = '';
  const m = s.mapping || {};
  if (m.eod) {
    const last = s.rows.filter(r=>r[m.eod] !== undefined && r[m.eod] !== "").slice(-1)[0];
    if (last) {
      addPill(`Last EoD: ${last[m.eod]}`);
    }
    const sum = s.rows.reduce((acc, r) => {
      const v = parseFloat(r[m.eod]);
      return acc + (isFinite(v)? v : 0);
    }, 0);
    addPill(`EoD Sum: ${sum.toFixed(2)}`);
  }
  if (m.allow) {
    const avg = s.rows.reduce((acc, r) => {
      const v = parseFloat(r[m.allow]);
      return acc + (isFinite(v)? v : 0);
    }, 0) / Math.max(1, s.rows.length);
    addPill(`Avg Allow: ${isFinite(avg)? avg.toFixed(2): '—'}`);
  }

  // table
  const mDate = s.mapping?.date || '';
  const mEod = s.mapping?.eod || '';
  const mAllow = s.mapping?.allow || '';
  const mComment = s.mapping?.comment || '';
  els.tableBody.innerHTML = '';

  s.rows.forEach((row, idx) => {
    const tr = document.createElement('tr');
    tr.appendChild(cellInput(row, mDate, idx, 'date'));
    tr.appendChild(cellInput(row, mEod, idx, 'eod'));
    tr.appendChild(cellInput(row, mAllow, idx, 'allow'));
    tr.appendChild(cellInput(row, mComment, idx, 'comment'));
    els.tableBody.appendChild(tr);
  });
}

function addPill(text) {
  const span = document.createElement('span');
  span.className = 'pill';
  span.textContent = text;
  els.summary.appendChild(span);
}

function cellInput(row, colName, rowIndex, logical) {
  const td = document.createElement('td');
  const input = document.createElement('input');
  input.className = 'cell';
  input.value = (colName && row[colName] != null) ? row[colName] : '';
  input.addEventListener('change', async (e) => {
    // Write back into the underlying column used by mapping
    const sheet = els.monthSelect.value;
    const s = state.sheets[sheet];
    const map = s.mapping || {};
    const realCol = map[logical];
    if (realCol) {
      s.rows[rowIndex][realCol] = e.target.value;
      await encryptState(state);
      renderSheet(sheet);
    } else {
      // If not mapped yet, do nothing
    }
  });
  td.appendChild(input);
  return td;
}

// ---------- Event wiring ----------
els.fileBtn.addEventListener('click', () => els.fileInput.click());
els.fileInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const data = await file.arrayBuffer();
  const wb = XLSX.read(data, { type: 'array' });
  const newSt = newState();
  newSt.workbookName = file.name;
  for (const name of wb.SheetNames) {
    const ws = wb.Sheets[name];
    const arr = XLSX.utils.sheet_to_json(ws, { defval: "" });
    const cols = Object.keys(arr[0] || {});
    newSt.sheets[name] = { columns: cols, rows: arr, mapping: guessMapping(cols) };
  }
  state = newSt;
  await encryptState(state);
  renderMonths();
  alert('Imported workbook locally.');
});

els.monthSelect.addEventListener('change', () => renderSheet(els.monthSelect.value));

els.btnSaveMapping.addEventListener('click', async () => {
  const sheet = els.monthSelect.value;
  const s = state.sheets[sheet];
  s.mapping = {
    date: els.mapDate.value || "",
    eod: els.mapEod.value || "",
    allow: els.mapAllow.value || "",
    comment: els.mapComment.value || ""
  };
  await encryptState(state);
  renderSheet(sheet);
});

els.settingsBtn.addEventListener('click', () => els.settingsDlg.showModal());

els.btnDeleteData.addEventListener('click', async () => {
  const a = prompt('Type DELETE to confirm you want to delete ALL local data.');
  if (a !== 'DELETE') return;
  const b = prompt('This cannot be undone. Type YES to proceed.');
  if (b !== 'YES') return;
  localStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(NONCE_KEY);
  // keep SALT so same PIN still works but data is gone
  state = newState();
  await encryptState(state);
  renderMonths();
  alert('All data cleared (state reset).');
});

els.btnChangePin.addEventListener('click', async () => {
  const current = prompt('Enter current passcode:');
  if (!current) return;
  const ok = await testPin(current);
  if (!ok) { alert('Incorrect current passcode.'); return; }
  const next = prompt('Enter new passcode (4–12 digits):');
  if (!next || next.length < 4 || next.length > 12) { alert('Invalid length.'); return; }
  gKey = await deriveKey(next);
  await encryptState(state || newState());
  alert('Passcode changed.');
});

els.btnExport.addEventListener('click', () => {
  const blob = new Blob([JSON.stringify(state || newState(), null, 2)], {type:'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'spending-plan.json';
  a.click();
  URL.revokeObjectURL(url);
});

els.btnUnlock.addEventListener('click', async () => {
  const pin = els.pin.value.trim();
  if (!pin || pin.length < 4 || pin.length > 12) {
    alert('Please enter a 4–12 digit passcode.');
    return;
  }
  gKey = await deriveKey(pin);
  const loaded = await tryLoad();
  if (!loaded) {
    state = newState();
    await encryptState(state);
  }
  setLocked(false);
  renderMonths();
});

async function testPin(pin) {
  const key = await deriveKey(pin);
  const prev = gKey;
  gKey = key;
  try {
    const st = await decryptState();
    gKey = prev;
    return !!st || (localStorage.getItem(STORAGE_KEY) === null);
  } catch {
    gKey = prev;
    return false;
  }
}

async function tryLoad() {
  try {
    const st = await decryptState();
    if (st) { state = st; return true; }
    return false;
  } catch {
    return false;
  }
}

// ---------- Mapping heuristic ----------
function guessMapping(cols) {
  const norm = s => s.toLowerCase().replace(/[^a-z0-9]/g,'');
  let date = cols.find(c => /date|day/i.test(c)) || cols[0] || "";
  let eod = cols.find(c => /end.*day.*bal|e.?o.?d|balance/i.test(norm(c))) || "";
  let allow = cols.find(c => /allow|budget|plan.*allow/i.test(norm(c))) || "";
  let comment = cols.find(c => /comment|note|memo/i.test(norm(c))) || "";
  return { date, eod, allow, comment };
}

// ---------- Init ----------
(function init() {
  // show lock; hint if first time
  const hasData = !!localStorage.getItem(STORAGE_KEY);
  els.hint.textContent = hasData
    ? 'Enter your passcode to unlock your data.'
    : 'First time? Set a PIN and we'll encrypt your data locally.';
  setLocked(true);
})();
