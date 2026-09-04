import { beforeEach, describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import LanguagePicker from "../src/components/LanguagePicker.vue";
import { locale } from "../src/i18n/index.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

const OPTIONS = [
  { code: "en", name: "English" },
  { code: "de", name: "Deutsch" },
];

beforeEach(async () => {
  await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.INPUT_AND_LANGUAGES, "Language row");
  locale.value = "en";
});

describe("LanguagePicker", () => {
  it("renders one button per configured language and marks the selected one", () => {
    const wrapper = mount(LanguagePicker, { props: { languages: OPTIONS, selected: "de" } });

    expect(wrapper.findAll(".lang-btn").map((button) => button.text())).toEqual([
      "English",
      "Deutsch",
    ]);
    expect(wrapper.get('[data-testid="lang-de"]').classes()).toContain("active");
    expect(wrapper.get('[data-testid="lang-en"]').classes()).not.toContain("active");
  });

  it("emits the code of the language pressed", async () => {
    const wrapper = mount(LanguagePicker, { props: { languages: OPTIONS, selected: "en" } });

    await wrapper.get('[data-testid="lang-de"]').trigger("click");

    expect(wrapper.emitted("update:selected")).toEqual([["de"]]);
  });

  // Nothing to switch between, but the row still names the language, and the pencil
  // beside it is the only way into the editor.
  it("keeps the row and the pencil with a single language", () => {
    const wrapper = mount(LanguagePicker, {
      props: { languages: [OPTIONS[0]], selected: "en" },
    });

    expect(wrapper.findAll(".lang-btn")).toHaveLength(1);
    expect(wrapper.get(".lang-btn").text()).toBe("English");
    expect(wrapper.find('[data-testid="edit-languages"]').exists()).toBe(true);
  });

  it("asks for the editor when the pencil is pressed", async () => {
    const wrapper = mount(LanguagePicker, { props: { languages: OPTIONS, selected: "en" } });

    await wrapper.get('[data-testid="edit-languages"]').trigger("click");

    expect(wrapper.emitted("edit")).toHaveLength(1);
  });

  // A table the app could not read is exactly when the editor has to stay reachable.
  it("keeps the pencil when there is no language to show", () => {
    const wrapper = mount(LanguagePicker, { props: { languages: [], selected: "" } });

    expect(wrapper.findAll(".lang-btn")).toEqual([]);
    expect(wrapper.get(".lang-none").text()).toBe("No language is configured.");
    expect(wrapper.get('[data-testid="edit-languages"]').exists()).toBe(true);
  });
});
