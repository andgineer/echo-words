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
