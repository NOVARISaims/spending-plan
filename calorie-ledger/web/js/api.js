// API client with bearer auth, cached reads and an offline mutation queue.
//
// Every mutation is an op {op_id, entity, action, payload} appended to the
// IndexedDB queue and flushed to POST /api/sync/batch. The server dedupes by
// op_id, so flushing after a dropped connection can never double-apply.

import { kvGet, kvSet, queueAll, queueCount, queueDelete, queuePush } from './idb.js';
import { emit, toast, uuid } from './util.js';

const TOKEN_KEY = 'ledger.token';
let flushing = false;
let offline = !navigator.onLine;

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function rawFetch(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, {
    method: opts.method || 'GET',
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401) {
    emit('auth-required');
    throw new ApiError(401, 'Not signed in');
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* keep statusText */ }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return res.json();
}

export async function api(path, opts) {
  try {
    const out = await rawFetch(path, opts);
    setOffline(false);
    return out;
  } catch (err) {
    if (err instanceof TypeError) setOffline(true); // network failure
    throw err;
  }
}

// GET with cache fallback: succeed -> cache; fail offline -> last cached copy.
export async function cachedGet(path) {
  try {
    const data = await api(path);
    kvSet(`cache:${path}`, { data, at: Date.now() });
    return { data, stale: false };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) throw err;
    const hit = await kvGet(`cache:${path}`);
    if (hit) return { data: hit.data, stale: true };
    throw err;
  }
}

// ------------------------------------------------------------- mutations
export async function mutate(entity, action, payload) {
  const op = { op_id: uuid(), entity, action, payload, ts: new Date().toISOString() };
  await queuePush(op);
  let results = await flushQueue();
  if (results === null && !offline) {
    // A concurrent flush was in-flight; give it a beat and pick up our op.
    await new Promise((r) => setTimeout(r, 400));
    results = await flushQueue();
  }
  const mine = results?.find((r) => r.op_id === op.op_id);
  if (!mine) {
    announceSync();
    return { status: 'queued', op_id: op.op_id };
  }
  if (mine.status === 'error') {
    toast(mine.error || 'Rejected by server', { bad: true, ms: 5000 });
  }
  return mine;
}

export async function flushQueue() {
  if (flushing) return null;
  flushing = true;
  try {
    const queued = await queueAll();
    if (!queued.length) { announceSync(); return []; }
    const ops = queued.map(({ seq, ...op }) => op);
    let body;
    try {
      body = await rawFetch('/api/sync/batch', { method: 'POST', body: { ops } });
      setOffline(false);
    } catch (err) {
      if (err instanceof TypeError || (err instanceof ApiError && err.status >= 500)) {
        setOffline(err instanceof TypeError);
        announceSync();
        return null; // keep queue, try again later
      }
      if (err instanceof ApiError && err.status === 401) throw err;
      throw err;
    }
    const results = body.results || [];
    for (const q of queued) {
      const r = results.find((x) => x.op_id === q.op_id);
      if (r) await queueDelete(q.seq); // applied, duplicate or rejected: done either way
    }
    announceSync();
    emit('data-changed');
    return results;
  } finally {
    flushing = false;
  }
}

function setOffline(v) {
  if (offline !== v) { offline = v; announceSync(); }
}

export async function announceSync() {
  const pending = await queueCount().catch(() => 0);
  emit('sync-status', { pending, offline });
}

export const isOffline = () => offline;

window.addEventListener('online', () => { setOffline(false); flushQueue(); });
window.addEventListener('offline', () => setOffline(true));
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) flushQueue().catch(() => {});
});
setInterval(() => { flushQueue().catch(() => {}); }, 45000);
