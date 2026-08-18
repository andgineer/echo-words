import { ref, watch } from "vue";
import { apiRequest } from "../api/_request.js";

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

export const languages = ref([]);
export const selected = ref(readStored());

watch(selected, (code) => {
  if (code) store(code);
});

export async function loadLanguages() {
  languages.value = await apiRequest("/api/languages");
  const known = languages.value.some((lang) => lang.code === selected.value);
  if (!known) selected.value = languages.value[0]?.code || "";
}

export function useLanguage() {
  return { languages, selected, loadLanguages };
}
