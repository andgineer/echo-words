import { ref, watch } from "vue";
import en from "./en.js";
import ru from "./ru.js";

const STORAGE_KEY = "echo-words.locale";
const FALLBACK = "en";

const CATALOGS = { ru, en };

export const LOCALES = [
  { code: "en", label: "EN" },
  { code: "ru", label: "RU" },
];

// Storage access throws outright in locked-down browser modes; remembering the
// interface language is not worth failing the whole app for.
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
    // the choice simply does not survive this visit
  }
}

function preferred() {
  const stored = readStored();
  return stored in CATALOGS ? stored : FALLBACK;
}

export const locale = ref(preferred());

watch(
  locale,
  (code) => {
    store(code);
    if (globalThis.document) globalThis.document.documentElement.lang = code;
  },
  { immediate: true },
);

export function t(key, params) {
  const template = CATALOGS[locale.value]?.[key] ?? CATALOGS[FALLBACK][key] ?? key;
  if (!params) return template;
  return template.replace(/\{(\w+)\}/gu, (placeholder, name) =>
    name in params ? String(params[name]) : placeholder,
  );
}

export function useI18n() {
  return { t, locale, locales: LOCALES };
}
