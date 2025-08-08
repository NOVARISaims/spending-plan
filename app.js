
/* No-PIN version: stores state in plain localStorage.
 * Key: 'sp-plan-plain'
 */
const els = {
  fileBtn: document.getElementById('btn-import'),
  fileInput: document.getElementById('file-input'),
  settingsBtn: document.getElementById('btn-settings'),
  settingsDlg: document.getElementById('settings'),
  btnDelete: document.getElementById('btn-delete-data'),
  monthSelect: document.getElementById('month-select'),
  mappingSec: document.getElementById('mapping'),
  mapDate: document.getElementById('map-date'),
  mapEod: document.getElementById('map-eod'),
  mapAllow: document.getElementById('map-allow'),
  mapComment: document.getElementById('map-comment'),
  btnSaveMapping: document.getElementById('btn-save-mapping'),
  tableBody: document.getElementById('data-body'),
  title: document.getElementById('sheet-title'),
  summary: document.getElementById('summary'),
  btnExport: document.getElementById('btn-export')
};

const STORAGE_KEY = 'sp-plan-plain';

let state = null;

function newState(){ return { version: 1, workbookName: "", sheets: {} }; }
function save(){ localStorage.setItem(STORAGE_KEY, JSON.stringify(state || newState())); }
function load(){
  try { state = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null'); }
  catch { state = null; }
  if (!state) { state = newState(); save(); }
}

function renderMonths(){
  const names = Object.keys(state.sheets);
  els.monthSelect.innerHTML = names.map(n => `<option>${n}</option>`).join('');
  if (names.length){
    els.monthSelect.value = names[0];
    renderSheet(names[0]);
  } else {
    els.title.textContent = 'No sheet loaded';
    els.tableBody.innerHTML = '';
  }
}

function ensureMapping(sheet){
  const s = state.sheets[sheet];
  const cols = s.columns;
  const map = s.mapping || {};
  [els.mapDate, els.mapEod, els.mapAllow, els.mapComment].forEach(sel => {
    sel.innerHTML = '<option value="">-- Select --</option>' + cols.map(c => `<option value="${c}">${c}</option>`).join('');
  });
  if (map.date) els.mapDate.value = map.date;
  if (map.eod) els.mapEod.value = map.eod;
  if (map.allow) els.mapAllow.value = map.allow;
  if (map.comment) els.mapComment.value = map.comment;
  els.mappingSec.classList.remove('hidden');
}

function addPill(text){
  const span = document.createElement('span');
  span.className = 'pill';
  span.textContent = text;
  els.summary.appendChild(span);
}

function cellInput(row, colName, rowIndex, logical){
  const td = document.createElement('td');
  const input = document.createElement('input');
  input.className = 'cell';
  input.value = (colName && row[colName] != null) ? row[colName] : '';
  input.addEventListener('change', () => {
    const sheet = els.monthSelect.value;
    const s = state.sheets[sheet];
    const map = s.mapping || {};
    const realCol = map[logical];
    if (realCol){
      s.rows[rowIndex][realCol] = input.value;
      save();
      renderSheet(sheet);
    }
  });
  td.appendChild(input);
  return td;
}

function renderSheet(name){
  const s = state.sheets[name];
  els.title.textContent = name;
  ensureMapping(name);

  els.summary.innerHTML = '';
  const m = s.mapping || {};
  if (m.eod){
    const last = s.rows.filter(r=>r[m.eod] !== undefined && r[m.eod] !== "").slice(-1)[0];
    if (last) addPill(`Last EoD: ${last[m.eod]}`);
    const sum = s.rows.reduce((acc, r) => {
      const v = parseFloat(r[m.eod]);
      return acc + (isFinite(v)? v : 0);
    }, 0);
    addPill(`EoD Sum: ${sum.toFixed(2)}`);
  }
  if (m.allow){
    const avg = s.rows.reduce((acc, r) => {
      const v = parseFloat(r[m.allow]);
      return acc + (isFinite(v)? v : 0);
    }, 0) / Math.max(1, s.rows.length);
    addPill(`Avg Allow: ${isFinite(avg)? avg.toFixed(2): '—'}`);
  }

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

// Events
els.fileBtn.addEventListener('click', () => els.fileInput.click());
els.fileInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const data = await file.arrayBuffer();
  const wb = XLSX.read(data, { type: 'array' });
  const newSt = newState();
  newSt.workbookName = file.name;
  for (const name of wb.SheetNames){
    const ws = wb.Sheets[name];
    const arr = XLSX.utils.sheet_to_json(ws, { defval: "" });
    const cols = Object.keys(arr[0] || {});
    newSt.sheets[name] = { columns: cols, rows: arr, mapping: guessMapping(cols) };
  }
  state = newSt;
  save();
  renderMonths();
  alert('Imported workbook locally.');
});

els.monthSelect.addEventListener('change', () => renderSheet(els.monthSelect.value));

els.btnSaveMapping.addEventListener('click', () => {
  const sheet = els.monthSelect.value;
  const s = state.sheets[sheet];
  s.mapping = {
    date: els.mapDate.value || "",
    eod: els.mapEod.value || "",
    allow: els.mapAllow.value || "",
    comment: els.mapComment.value || ""
  };
  save();
  renderSheet(sheet);
});

els.settingsBtn.addEventListener('click', () => els.settingsDlg.showModal());

els.btnDelete.addEventListener('click', () => {
  const a = prompt('Type DELETE to confirm you want to delete ALL local data.');
  if (a !== 'DELETE') return;
  const b = prompt('This cannot be undone. Type YES to proceed.');
  if (b !== 'YES') return;
  localStorage.removeItem(STORAGE_KEY);
  state = newState();
  save();
  renderMonths();
  alert('All data cleared (state reset).');
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

function guessMapping(cols){
  const norm = s => s.toLowerCase().replace(/[^a-z0-9]/g,'');
  let date = cols.find(c => /date|day/i.test(c)) || cols[0] || "";
  let eod = cols.find(c => /end.*day.*bal|e.?o.?d|balance/i.test(norm(c))) || "";
  let allow = cols.find(c => /allow|budget|plan.*allow/i.test(norm(c))) || "";
  let comment = cols.find(c => /comment|note|memo/i.test(norm(c))) || "";
  return { date, eod, allow, comment };
}

(function init(){
  load();
  renderMonths();
})();
