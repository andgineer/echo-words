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

// A counted message is keyed by CLDR plural category, so the runtime picks the form:
// Russian alone needs four of them, and 5 карточек is "many", not "other".
export function tn(key, count, params) {
  const form = new Intl.PluralRules(locale.value).select(count);
  return t(`${key}.${form}`, { count, ...params });
}

export function useI18n() {
  return { t, tn, locale, locales: LOCALES };
}
