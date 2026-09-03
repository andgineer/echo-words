import { ref } from "vue";

// The server keeps the same number and evicts the same way, but the browser only
// re-syncs to it on a stream reconnect, so a tab left open for weeks would keep
// everything the stream ever sent.
const MAX_ENTRIES = 50;

export const entries = ref([]);

export function replaceEntries(snapshot) {
  entries.value = snapshot;
}

export function upsertEntry(entry, { newest = false } = {}) {
  const index = entries.value.findIndex((item) => item.entry_id === entry.entry_id);
  if (index === -1) {
    if (newest) entries.value.unshift(entry);
    else entries.value.push(entry);
    trim();
    return;
  }
  entries.value[index] = { ...entries.value[index], ...entry };
}

// Oldest first, and never an entry still waiting on the pipeline: dropping one
// would leave an answer with nowhere to land.
function trim() {
  let index = entries.value.length - 1;
  while (index >= 0 && entries.value.length > MAX_ENTRIES) {
    if (entries.value[index].status !== "pending") entries.value.splice(index, 1);
    index -= 1;
  }
}

export function useEntries() {
  return { entries, replaceEntries, upsertEntry };
}
