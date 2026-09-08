import { apiRequest } from "./_request.js";

// This identity belongs to user data, not to a build or service-worker version.
export const DATABASE_NAME = "echo-words";
export const DAY_MS = 24 * 60 * 60 * 1000;
const STORE = "cache";
const FALLBACK_PREFIX = "echo-words.cache.v1:";
const records = new Map();
const pending = new Map();
let database = null;
let initialization = null;

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, 1);
    let abandoned = false;
    function fail(error = new Error("Browser storage blocked")) {
      abandoned = true;
      clearTimeout(timeout);
      reject(error);
    }
    const timeout = setTimeout(fail, 1500);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: "key" });
    };
    request.onerror = () => fail(request.error);
    request.onblocked = () => fail();
    request.onsuccess = () => {
      clearTimeout(timeout);
      if (abandoned) { request.result.close(); return; }
      const db = request.result;
      db.onversionchange = () => { db.close(); database = null; };
      resolve(db);
    };
  });
}

function readDatabase(db) {
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE, "readonly");
    const request = transaction.objectStore(STORE).getAll();
    transaction.oncomplete = () => resolve(request.result);
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

export function initializeCache() {
  if (initialization) return initialization;
  initialization = (async () => {
    try {
      database = await openDatabase();
      for (const saved of await readDatabase(database)) {
        if (saved && Number.isFinite(saved.fetchedAt)) records.set(saved.key, saved);
      }
    } catch {
      // Storage failures fall back to localStorage, then to this visit's memory.
      database?.close();
      database = null;
    }
  })();
  return initialization;
}

export function requestPersistentStorage() {
  void navigator.storage?.persist?.().catch(() => {});
}

export function _resetForTest() {
  database?.close();
  database = null;
  initialization = null;
  records.clear();
  pending.clear();
}

export function readCache(key) {
  const current = records.get(key);
  try {
    const fallback = JSON.parse(localStorage.getItem(`${FALLBACK_PREFIX}${key}`));
    if (fallback && Number.isFinite(fallback.fetchedAt)
        && (!current || fallback.updatedAt > current.updatedAt)) return fallback;
  } catch {
    // Locked-down browser modes may refuse even a read.
  }
  return current ?? null;
}

function writeFallback(key, saved) {
  try {
    localStorage.setItem(`${FALLBACK_PREFIX}${key}`, JSON.stringify(saved));
  } catch {
    // A full quota must not stop the current answer reaching the page.
  }
}

export function writeCache(key, data, fetchedAt = Date.now(), attemptedAt = fetchedAt) {
  // Vue proxies cannot be cloned by IndexedDB; capture the value before queuing it.
  const saved = JSON.parse(JSON.stringify({ key, data, fetchedAt, attemptedAt, updatedAt: Date.now() }));
  records.set(key, saved);
  if (!database) {
    writeFallback(key, saved);
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    try {
      const transaction = database.transaction(STORE, "readwrite");
      transaction.objectStore(STORE).put(saved);
      transaction.oncomplete = () => resolve();
      transaction.onerror = transaction.onabort = () => { writeFallback(key, saved); resolve(); };
    } catch {
      writeFallback(key, saved);
      resolve();
    }
  });
}

export function invalidateCache(key) {
  const cached = readCache(key);
  if (cached) void writeCache(key, cached.data, 0, 0);
}

export async function cachedRequest(path, { validate = Array.isArray, background = false } = {}) {
  const cached = readCache(path);
  const usable = cached && validate(cached.data);
  const lastAttempt = cached?.attemptedAt ?? cached?.fetchedAt;
  if (pending.has(path)) return usable && background ? cached.data : pending.get(path);
  if (usable && Date.now() - lastAttempt < DAY_MS) return cached.data;
  // A failed refresh also counts toward the daily network budget. An empty
  // database can retry whenever connectivity returns.
  if (usable) void writeCache(path, cached.data, cached.fetchedAt, Date.now());
  const request = (async () => {
    try {
      const data = await apiRequest(path, { timeoutMs: 8000 });
      if (!validate(data)) throw new Error("Invalid server response");
      await writeCache(path, data);
      return data;
    } catch (error) {
      if (usable) return cached.data;
      throw error;
    } finally {
      pending.delete(path);
    }
  })();
  pending.set(path, request);
  if (usable && background) {
    void request.catch(() => {});
    return cached.data;
  }
  return request;
}
