// Boot: auth gate, tab router, sync chip, service worker, deep links.

import { announceSync, api, cachedGet, flushQueue, getToken, setToken } from './api.js';
import { S } from './store.js';
import { $, $$, on, toast } from './util.js';
import * as today from './tabs/today.js';
import * as scan from './tabs/scan.js';
import * as log from './tabs/log.js';
import * as progress from './tabs/progress.js';
import * as settings from './tabs/settings.js';

const TABS = { today, scan, log, progress, settings };
let active = null;

async function loadSettings() {
  try {
    const res = await cachedGet('/api/settings');
    S.settings = res.data;
  } catch { /* keep whatever we have; tabs cope with null */ }
}

async function showTab(name) {
  if (!TABS[name]) name = 'today';
  if (active && TABS[active].onLeave) TABS[active].onLeave();
  active = name;
  S.tab = name;
  $$('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
  const view = $('#view');
  view.scrollTop = 0;
  // Fresh mount per render so per-tab event listeners never accumulate.
  const mount = document.createElement('div');
  view.replaceChildren(mount);
  await TABS[name].render(mount);
}

function bindNav() {
  $('#tabbar').addEventListener('click', (e) => {
    const tab = e.target.closest('.tab');
    if (tab) showTab(tab.dataset.tab);
  });
  $('#sync-chip').addEventListener('click', async () => {
    await flushQueue().catch(() => {});
    toast('Sync attempted');
  });
}

function bindSyncChip() {
  on('sync-status', ({ pending, offline }) => {
    const chip = $('#sync-chip');
    if (offline) {
      chip.textContent = pending ? `⚠ ${pending}` : '⚠ offline';
      chip.className = 'sync-chip offline';
      chip.title = 'Offline — queued changes will sync automatically';
    } else if (pending) {
      chip.textContent = `↑ ${pending}`;
      chip.className = 'sync-chip pending';
      chip.title = `${pending} change(s) waiting to sync`;
    } else {
      chip.textContent = '✓';
      chip.className = 'sync-chip';
      chip.title = 'All changes synced';
    }
  });
}

function applyDeepLink(url) {
  const params = new URLSearchParams(url.split('?')[1] || '');
  const tab = params.get('tab');
  const meal = params.get('meal');
  if (meal && tab === 'log') log.setDeepLink({ meal });
  if (tab) showTab(tab);
}

async function showLogin() {
  $('#app').classList.add('hidden');
  $('#login').classList.remove('hidden');
  const form = $('#login-form');
  const err = $('#login-error');
  form.onsubmit = async (e) => {
    e.preventDefault();
    err.hidden = true;
    const passphrase = $('#login-pass').value;
    try {
      const res = await api('/api/auth/login', {
        method: 'POST',
        body: { passphrase, label: navigator.userAgent.includes('iPhone') ? 'iPhone' : 'browser' },
      });
      setToken(res.token);
      $('#login-pass').value = '';
      await startApp();
    } catch (ex) {
      err.textContent = ex.status === 429 ? 'Too many attempts — wait a moment.'
        : ex.status === 401 ? 'Wrong passphrase.' : `Cannot reach server (${ex.message}).`;
      err.hidden = false;
    }
  };
}

async function startApp() {
  $('#login').classList.add('hidden');
  $('#app').classList.remove('hidden');
  await loadSettings();
  await announceSync();
  flushQueue().catch(() => {});
  const params = new URLSearchParams(location.search);
  if (params.get('meal') && (params.get('tab') || 'log') === 'log') {
    log.setDeepLink({ meal: params.get('meal') });
  }
  await showTab(params.get('tab') || 'today');
}

function registerSW() {
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.register('/sw.js').catch(() => {});
  navigator.serviceWorker.addEventListener('message', (e) => {
    if (e.data?.type === 'navigate') applyDeepLink(e.data.url);
  });
}

async function boot() {
  bindNav();
  bindSyncChip();
  registerSW();
  on('auth-required', () => { setToken(null); showLogin(); });
  on('data-changed', async () => {
    await loadSettings();
    if (active === 'today') showTab('today');
  });
  on('render-tab', () => { if (active) showTab(active); });

  if (!getToken()) { await showLogin(); return; }
  try {
    await api('/api/auth/session');
    await startApp();
  } catch (err) {
    if (err.status === 401) await showLogin();
    else await startApp(); // offline with a token: run from cache
  }
}

boot();
