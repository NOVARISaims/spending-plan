// IndexedDB: offline op queue + key-value cache for API GETs.

const DB_NAME = 'calorie-ledger';
const DB_VERSION = 1;
let dbPromise = null;

function open() {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains('queue')) {
          db.createObjectStore('queue', { keyPath: 'seq', autoIncrement: true });
        }
        if (!db.objectStoreNames.contains('kv')) {
          db.createObjectStore('kv');
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  return dbPromise;
}

function tx(store, mode, fn) {
  return open().then((db) => new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const s = t.objectStore(store);
    const out = fn(s);
    t.oncomplete = () => resolve(out?.result ?? out);
    t.onerror = () => reject(t.error);
  }));
}

export const queuePush = (op) => tx('queue', 'readwrite', (s) => s.add(op));

export const queueAll = () => tx('queue', 'readonly', (s) => s.getAll())
  .then((r) => r || []);

export const queueDelete = (seq) => tx('queue', 'readwrite', (s) => s.delete(seq));

export const queueCount = () => tx('queue', 'readonly', (s) => s.count());

export const kvSet = (key, value) => tx('kv', 'readwrite', (s) => s.put(value, key));

export const kvGet = (key) => tx('kv', 'readonly', (s) => s.get(key));

export const kvClear = () => tx('kv', 'readwrite', (s) => s.clear());
