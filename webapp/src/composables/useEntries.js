import { ref } from "vue";
import { readCache, writeCache } from "../api/cache.js";

export const MAX_ENTRIES = 50;
const HISTORY_KEY = "history";
const cached = readCache(HISTORY_KEY)?.data;

export const entries = ref(Array.isArray(cached) ? cached : []);

export function restoreEntries() {
  const saved = readCache(HISTORY_KEY)?.data;
  entries.value = Array.isArray(saved) ? saved : [];
  trim();
}

export function replaceEntries(snapshot) {
  entries.value = snapshot;
  trim();
  writeCache(HISTORY_KEY, entries.value);
}

export function upsertEntry(entry, { newest = false } = {}) {
  const index = entries.value.findIndex((item) => item.entry_id === entry.entry_id);
  if (index === -1) {
    if (newest) entries.value.unshift(entry);
    else entries.value.push(entry);
    trim();
    writeCache(HISTORY_KEY, entries.value);
    return;
  }
  entries.value[index] = { ...entries.value[index], ...entry };
  trim();
  writeCache(HISTORY_KEY, entries.value);
}

// A receipt can be read after the events it would overwrite. Once a reverse lookup has
// renamed the entry, or its answer moved it to another tab, what was submitted is no
// longer what the entry is.
export function applyReceipt(receipt) {
  const known = entries.value.find((entry) => entry.entry_id === receipt.entry_id);
  const fields = { ...receipt };
  if (known?.typed_word) {
    for (const key of ["word", "context", "requested_shape", "requested_reverse"]) {
      delete fields[key];
    }
  }
  if (known?.moved) {
    delete fields.lang;
    delete fields.language;
  }
  upsertEntry(known ? fields : { ...fields, status: "pending" }, { newest: true });
}

// Each language is bounded on its own, so a busy one never empties another's rail.
// Oldest first, and never an entry still waiting on the pipeline: dropping one
// would leave an answer with nowhere to land.
function trim() {
  const counts = new Map();
  for (const { lang } of entries.value) counts.set(lang, (counts.get(lang) ?? 0) + 1);
  for (let index = entries.value.length - 1; index >= 0; index -= 1) {
    const { lang, status } = entries.value[index];
    if (counts.get(lang) <= MAX_ENTRIES || status === "pending") continue;
    entries.value.splice(index, 1);
    counts.set(lang, counts.get(lang) - 1);
  }
}

export function useEntries() {
  return { entries, replaceEntries, upsertEntry };
}
