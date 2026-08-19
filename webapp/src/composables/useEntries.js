import { ref } from "vue";

export const entries = ref([]);

export function replaceEntries(snapshot) {
  entries.value = snapshot;
}

export function upsertEntry(entry, { newest = false } = {}) {
  const index = entries.value.findIndex((item) => item.entry_id === entry.entry_id);
  if (index === -1) {
    if (newest) entries.value.unshift(entry);
    else entries.value.push(entry);
    return;
  }
  entries.value[index] = { ...entries.value[index], ...entry };
}

export function useEntries() {
  return { entries, replaceEntries, upsertEntry };
}

