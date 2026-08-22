import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../src/composables/useResendQueue.js", () => ({ flushQueue: vi.fn() }));
vi.mock("../src/views/StatsView.vue", () => ({ default: { template: "<div />" } }));
vi.mock("../src/views/StatusView.vue", () => ({ default: { template: "<div />" } }));
vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

import App from "../src/App.vue";
import en from "../src/i18n/en.js";
import ru from "../src/i18n/ru.js";
import { apiRequest } from "../src/api/_request.js";
import { languages, selected } from "../src/composables/useLanguage.js";
import { locale, t } from "../src/i18n/index.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

beforeEach(async () => {
  await labelBehavior(EPIC.APPLICATION_PLATFORM, FEATURE.INTERFACE_LANGUAGE);
  localStorage.clear();
  locale.value = "en";
  languages.value = [];
  selected.value = "";
  apiRequest.mockReset();
  apiRequest.mockResolvedValue([{ code: "en", name: "English" }]);
});

afterEach(() => {
  locale.value = "en";
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("interface language", () => {
  it("covers every message in both catalogues", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(ru).sort());
  });

  it("interpolates named placeholders and passes an unknown key through", () => {
    expect(t("add.undone", { word: "Straße" })).toBe("Removed: Straße");
    locale.value = "ru";
    expect(t("add.undone", { word: "Straße" })).toBe("Удалено: Straße");
    expect(t("add.undone")).toBe("Удалено: {word}");
    expect(t("nothing.here")).toBe("nothing.here");
  });

  it("starts in English and remembers the chosen language across reloads", async () => {
    expect(t("nav.words")).toBe("Words");

    locale.value = "ru";
    await nextTick();
    expect(localStorage.getItem("echo-words.locale")).toBe("ru");
    expect(document.documentElement.lang).toBe("ru");

    vi.resetModules();
    const reloaded = await import("../src/i18n/index.js");
    expect(reloaded.locale.value).toBe("ru");
    expect(reloaded.t("nav.words")).toBe("Слова");
  });

  it("ignores a stored language that no catalogue provides", async () => {
    localStorage.setItem("echo-words.locale", "fr");
    vi.resetModules();
    const reloaded = await import("../src/i18n/index.js");

    expect(reloaded.locale.value).toBe("en");
  });

  it("switches the whole interface from the header selector", async () => {
    const wrapper = mount(App);
    await flushPromises();
    expect(wrapper.find("nav").text()).toContain("Words");
    expect(wrapper.text()).toContain("Analyse");

    await wrapper.find("select.locale").setValue("ru");
    await flushPromises();

    expect(wrapper.find("nav").text()).toContain("Слова");
    expect(wrapper.text()).toContain("Разобрать");
    expect(wrapper.text()).toContain("Только посмотреть");
    expect(wrapper.text()).not.toContain("Analyse");
  });
});
