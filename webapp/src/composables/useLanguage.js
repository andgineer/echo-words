import { ref, watch } from "vue";
import { cachedRequest, invalidateCache, readCache } from "../api/cache.js";

const STORAGE_KEY = "echo-words.lang";

// Storage access throws outright in locked-down browser modes; remembering the
// selector is not worth failing the whole app for.
function readStored() {
  try {
    return localStorage.getItem(STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function store(code) {
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    // the selection simply does not survive this visit
  }
}

const cached = readCache("/api/languages")?.data;
export const languages = ref(Array.isArray(cached) ? cached : []);
export const selected = ref(readStored());

function selectKnown() {
  const known = languages.value.some((lang) => lang.code === selected.value);
  if (!known) selected.value = languages.value[0]?.code || "";
}

if (languages.value.length) selectKnown();

export function restoreLanguages() {
  const saved = readCache("/api/languages")?.data;
  languages.value = Array.isArray(saved) ? saved : [];
  if (languages.value.length) selectKnown();
}

watch(selected, (code) => {
  if (code) store(code);
});

export async function loadLanguages() {
  languages.value = await cachedRequest("/api/languages");
  selectKnown();
}

export function invalidateLanguages() {
  invalidateCache("/api/languages");
  invalidateCache("/api/languages/config");
}

export async function refreshReferences() {
  await Promise.allSettled([
    loadLanguages(),
    cachedRequest("/api/languages/config"),
    cachedRequest("/api/languages/catalog"),
  ]);
}

export function useLanguage() {
  return { languages, selected, loadLanguages };
}
