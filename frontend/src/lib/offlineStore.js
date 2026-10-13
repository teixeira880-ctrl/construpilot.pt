// Minimal IndexedDB wrapper for offline chantier mode (no external deps).
const DB_NAME = "construpilot-offline";
const DB_VERSION = 1;
const STORE_SNAP = "snapshots"; // key: `${userId}:${kind}` → value
const STORE_QUEUE = "queue";    // auto-increment: {userId, method, url, body, entity, ts, label}

let _dbPromise = null;

function openDB() {
  if (_dbPromise) return _dbPromise;
  _dbPromise = new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") { reject(new Error("no-indexeddb")); return; }
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_SNAP)) db.createObjectStore(STORE_SNAP);
      if (!db.objectStoreNames.contains(STORE_QUEUE)) {
        const q = db.createObjectStore(STORE_QUEUE, { keyPath: "id", autoIncrement: true });
        q.createIndex("userId", "userId", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return _dbPromise;
}

function tx(store, mode, fn) {
  return openDB().then((db) => new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const s = t.objectStore(store);
    const out = fn(s);
    t.oncomplete = () => resolve(out?._result !== undefined ? out._result : out);
    t.onerror = () => reject(t.error);
    t.onabort = () => reject(t.error);
  }));
}

export async function snapSet(userId, kind, value) {
  try { await tx(STORE_SNAP, "readwrite", (s) => s.put(value, `${userId}:${kind}`)); } catch { /* offline store unavailable */ }
}

export async function snapGet(userId, kind) {
  try {
    return await tx(STORE_SNAP, "readonly", (s) => {
      const r = s.get(`${userId}:${kind}`);
      const holder = {};
      r.onsuccess = () => { holder._result = r.result; };
      return holder;
    });
  } catch { return undefined; }
}

export async function queueAdd(mutation) {
  try { await tx(STORE_QUEUE, "readwrite", (s) => s.add({ ...mutation, ts: Date.now() })); } catch { /* ignore */ }
}

export async function queueList(userId) {
  try {
    return await tx(STORE_QUEUE, "readonly", (s) => {
      const holder = { _result: [] };
      const idx = s.index("userId");
      const r = idx.getAll(userId);
      r.onsuccess = () => { holder._result = r.result || []; };
      return holder;
    }) || [];
  } catch { return []; }
}

export async function queueRemove(id) {
  try { await tx(STORE_QUEUE, "readwrite", (s) => s.delete(id)); } catch { /* ignore */ }
}

export async function clearForUser(userId) {
  try {
    const items = await queueList(userId);
    await Promise.all(items.map((i) => queueRemove(i.id)));
    await tx(STORE_SNAP, "readwrite", (s) => { s.delete(`${userId}:projects`); });
  } catch { /* ignore */ }
}
