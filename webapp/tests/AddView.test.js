import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

import { apiRequest } from "../src/api/_request.js";
import { languages, selected } from "../src/composables/useLanguage.js";
import AddView from "../src/views/AddView.vue";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

const OPTIONS = [
  { code: "en", name: "English" },
  { code: "de", name: "Deutsch" },
];

beforeEach(async () => {
  await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.INPUT_AND_LANGUAGES, "Word submission");
  languages.value = [];
  selected.value = "";
  localStorage.clear();
  apiRequest.mockReset();
  apiRequest.mockImplementation(async (path) => {
    if (path === "/api/languages") return OPTIONS;
    throw new Error(`Unexpected request: ${path}`);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("AddView", () => {
  it("renders the configured language selector and M1 controls", async () => {
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.findAll("#lang option").map((option) => option.text())).toEqual([
      "English",
      "Deutsch",
    ]);
    expect(wrapper.find("#word").exists()).toBe(true);
    expect(wrapper.find('.lookup input[type="checkbox"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("Только посмотреть");
    expect(wrapper.text()).toContain("Здесь появятся разборы слов");
  });

  it("submits the selected language and lookup-only flag, then renders the pending entry", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") {
        return {
          entry_id: "entry-1",
          word: "Straße",
          lang: "de",
          language: "Deutsch",
          lookup_only: true,
          context: "",
        };
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find("#lang").setValue("de");
    await wrapper.find("#word").setValue("Straße");
    await wrapper.find('.lookup input[type="checkbox"]').setValue(true);

    await wrapper.find(".btn-primary").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/words", {
      method: "POST",
      body: { word: "Straße", lang: "de", lookup_only: true },
    });
    expect(wrapper.find(".entry-head").text()).toContain("Straße");
    expect(wrapper.find(".entry-meta").text()).toContain("Deutsch · без карточки");
    expect(wrapper.find("#word").element.value).toBe("");
    expect(wrapper.find('.lookup input[type="checkbox"]').element.checked).toBe(false);
  });

  it("shows a backend validation hint without creating an entry", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      throw new Error("Для «English» нужна латиница.");
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find("#word").setValue("слово");

    await wrapper.find(".btn-primary").trigger("click");
    await flushPromises();

    expect(wrapper.find(".hint").text()).toBe("Для «English» нужна латиница.");
    expect(wrapper.find(".entry").exists()).toBe(false);
  });

  it("documents both lookup shortcuts and the reversible correction control", async () => {
    const wrapper = mount(AddView);
    await flushPromises();

    await wrapper.find(".btn-inline").trigger("click");

    expect(wrapper.find(".about-text").text()).toContain("? слово");
    expect(wrapper.find(".about-text").text()).toContain("✏️ Исправить");
    expect(wrapper.find(".about-text").text()).toContain("вернуться обратно");
  });
});
