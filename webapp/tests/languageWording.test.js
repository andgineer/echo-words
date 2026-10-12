import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { catalog, target } from "../src/composables/useTarget.js";
import { locale } from "../src/i18n/index.js";
import {
  placeholder,
  reverseOffer,
  reversing,
  translatedFrom,
} from "../src/i18n/languageWording.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

const DIRECTORY = [
  { code: "en", english: "English", russian: "английский", script: "latin" },
  { code: "de", english: "German", russian: "немецкий", script: "latin" },
  { code: "sr", english: "Serbian", russian: "сербский", script: "latin+cyrillic" },
  { code: "ru", english: "Russian", russian: "русский", script: "cyrillic" },
  { code: "sw", english: "Swahili", russian: "суахили", script: "latin" },
  { code: "fr", english: "French", russian: "французский", script: "latin" },
];
const RUSSIAN = { code: "ru", name: "Russian" };
const SWAHILI = { code: "sw", name: "Swahili" };
const OUTSIDE = { code: null, name: "Japanese" };

beforeEach(async () => {
  await labelBehavior(EPIC.APPLICATION_PLATFORM, FEATURE.INTERFACE_LANGUAGE, "Language names");
  catalog.value = DIRECTORY;
  target.value = RUSSIAN;
  locale.value = "en";
});

afterEach(() => {
  catalog.value = [];
  target.value = null;
  locale.value = "en";
});

describe("what the empty field says it takes", () => {
  it.each([
    // The tab and the target are written in different alphabets: either is just typed.
    ["ru", "en", RUSSIAN, "Русский или английский"],
    ["en", "en", RUSSIAN, "Russian or English"],
    ["ru", "de", RUSSIAN, "Русский или немецкий"],
    ["ru", "sw", RUSSIAN, "Русский или суахили"],
    ["en", "sw", RUSSIAN, "Russian or Swahili"],
    // They share an alphabet: the target needs its shortcut.
    ["ru", "sr", RUSSIAN, "Текст или !русский текст"],
    ["en", "sr", RUSSIAN, "Text or !Russian text"],
    // A name that does not decline gets a wording built around it.
    ["ru", "en", SWAHILI, "Текст или !текст на суахили"],
    ["en", "en", SWAHILI, "Text or !Swahili text"],
    // A target outside the directory has no known alphabet and only its own name.
    ["ru", "en", OUTSIDE, "Текст или !текст на Japanese"],
    ["en", "en", OUTSIDE, "Text or !Japanese text"],
    // A tab outside the directory keeps the shortcut, which works everywhere.
    ["ru", "xx", RUSSIAN, "Текст или !русский текст"],
  ])("in %s on the %s tab", (interfaceLanguage, tab, translatedInto, expected) => {
    locale.value = interfaceLanguage;
    target.value = translatedInto;

    expect(placeholder(tab)).toBe(expected);
  });

  it("promises nothing about a target it has not been told yet", () => {
    target.value = null;

    expect(placeholder("en")).toBe("A word or a text");
    locale.value = "ru";
    expect(placeholder("en")).toBe("Слово или текст");
  });
});

describe("the reverse lookup's wording", () => {
  it("names the tab's language while the word is being found", () => {
    const entry = { word: "стол", lang: "en", language: "English" };

    expect(reversing(entry)).toBe("Translating «стол» into English…");
    locale.value = "ru";
    expect(reversing(entry)).toBe("Перевожу «стол» на английский…");
    expect(reversing({ ...entry, lang: "sw" })).toBe("Перевожу «стол» на суахили…");
  });

  it("falls back to the tab's own name for a language outside the directory", () => {
    expect(reversing({ word: "стол", lang: "xx", language: "Xxish" })).toBe(
      "Translating «стол» into Xxish…",
    );
  });

  it("offers the target reading in the target's name", () => {
    expect(reverseOffer()).toBe("Look it up as a word in Russian");
    locale.value = "ru";
    expect(reverseOffer()).toBe("Искать как русское слово");

    target.value = SWAHILI;
    expect(reverseOffer()).toBe("Искать как слово на суахили");
    target.value = OUTSIDE;
    expect(reverseOffer()).toBe("Искать как слово на Japanese");
    target.value = null;
    expect(reverseOffer()).toBe("Искать как слово на языке перевода");
  });

  it("names the language input was translated from", () => {
    expect(translatedFrom("fr")).toBe("Translated from French");
    locale.value = "ru";
    expect(translatedFrom("fr")).toBe("Перевод с французского");
    expect(translatedFrom("sw")).toBe("Перевод с языка суахили");
  });

  it("names a language the directory does not carry as the browser does", () => {
    expect(translatedFrom("ja")).toBe("Translated from Japanese");
    locale.value = "ru";
    expect(translatedFrom("ja")).toBe("Перевод с японского");
    expect(translatedFrom("hi")).toBe("Перевод с языка хинди");
  });

  it("says so when nobody knows the language named", () => {
    expect(translatedFrom("")).toBe("Translated from another language");
    expect(translatedFrom(null)).toBe("Translated from another language");
  });
});
