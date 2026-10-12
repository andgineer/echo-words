import { catalog, target } from "../composables/useTarget.js";
import { locale, t } from "./index.js";

// A Russian language name is an adjective that declines (сербский), or a noun that does
// not (суахили): the first takes an ending, the second a wording built around it.
const ADJECTIVE = /(?:ий|ый|ой)$/u;

// The catalogues hold the sentences; these are the forms of a language's name those
// sentences need, which is grammar and differs per interface language.
const FORMS = {
  ru: {
    text: (name) => (ADJECTIVE.test(name) ? `${name} текст` : `текст на ${name}`),
    word: (name) =>
      ADJECTIVE.test(name) ? `${name.replace(ADJECTIVE, "ое")} слово` : `слово на ${name}`,
    from: (name) => (ADJECTIVE.test(name) ? name.replace(ADJECTIVE, "ого") : `языка ${name}`),
  },
  en: {
    text: (name) => `${name} text`,
    word: (name) => `a word in ${name}`,
    from: (name) => name,
  },
};

function forms() {
  return FORMS[locale.value] ?? FORMS.en;
}

function listed(code) {
  return (code && catalog.value.find((entry) => entry.code === code)) || null;
}

function browserName(code) {
  try {
    const name = new Intl.DisplayNames([locale.value], { type: "language" }).of(code);
    return name && name !== code ? name : "";
  } catch {
    return "";
  }
}

// What the interface language calls a language, or nothing where nobody knows it.
function nameOf(code) {
  const row = listed(code);
  if (row) return locale.value === "ru" ? row.russian : row.english;
  return code ? browserName(code) : "";
}

function targetName() {
  const named = target.value;
  if (!named) return "";
  return nameOf(named.code) || named.name;
}

function capitalized(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function sharesAlphabet(first, second) {
  const theirs = second.split("+");
  return first.split("+").some((script) => theirs.includes(script));
}

// What the empty field takes on this tab. Where the tab's language and the target are
// written in different alphabets, either is simply typed; where they share one, the
// target needs its `!`.
export function placeholder(sourceCode) {
  if (!target.value) return t("add.placeholder");
  const source = listed(sourceCode);
  const theirs = listed(target.value.code);
  if (!source || !theirs || sharesAlphabet(source.script, theirs.script)) {
    return t("add.placeholderShared", { target: forms().text(targetName()) });
  }
  // The two bare names, with no noun after them: the longest pair the directory holds
  // has to fit a phone's field, and a bare name needs no ending either.
  return capitalized(
    t("add.placeholderApart", { target: nameOf(theirs.code), source: nameOf(source.code) }),
  );
}

export function reversing(entry) {
  const language = nameOf(entry.lang) || entry.language || entry.lang;
  return t("add.reversing", { word: entry.word, language });
}

export function translatedFrom(code) {
  const name = nameOf(code);
  return name ? t("add.foreign", { language: forms().from(name) }) : t("add.foreignUnknown");
}

export function reverseOffer() {
  const name = targetName();
  return name ? t("add.reverseOffer", { target: forms().word(name) }) : t("add.reverseOfferUnknown");
}
