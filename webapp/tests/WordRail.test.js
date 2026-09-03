import { beforeEach, describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import WordRail from "../src/components/WordRail.vue";
import { locale } from "../src/i18n/index.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

const SENTENCE = "Сутра идем на посао, а данас читам књигу код куће.";

function rail(entries, selectedId = "entry-1") {
  return mount(WordRail, { props: { entries, selectedId } });
}

beforeEach(async () => {
  await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.HISTORY, "Word rail");
  locale.value = "en";
});

describe("WordRail", () => {
  it("lists a chip per entry in the order given and marks the selected one", () => {
    const wrapper = rail(
      [
        { entry_id: "entry-2", word: "прозор", status: "done" },
        { entry_id: "entry-1", word: "кућа", status: "done" },
      ],
      "entry-1",
    );

    expect(wrapper.findAll(".chip").map((chip) => chip.text())).toEqual(["прозор", "кућа"]);
    expect(wrapper.get('[data-testid="chip-entry-1"]').classes()).toContain("active");
    expect(wrapper.get('[data-testid="chip-entry-2"]').classes()).not.toContain("active");
  });

  it("emits the entry a chip stands for when it is tapped", async () => {
    const wrapper = rail([
      { entry_id: "entry-1", word: "кућа", status: "done" },
      { entry_id: "entry-2", word: "прозор", status: "done" },
    ]);

    await wrapper.get('[data-testid="chip-entry-2"]').trigger("click");

    expect(wrapper.emitted("select")).toEqual([["entry-2"]]);
  });

  // The chip is bounded by CSS, not by cutting the text: the full sentence stays
  // readable through the tooltip and the rail keeps its place in the DOM.
  it("keeps a sentence chip's whole text while bounding its width", () => {
    const wrapper = rail([{ entry_id: "entry-1", word: SENTENCE, status: "done" }]);

    const chip = wrapper.get(".chip");
    expect(chip.text()).toBe(SENTENCE);
    expect(chip.attributes("title")).toBe(SENTENCE);
  });

  it("marks a pending entry and one whose paid call is running as live", () => {
    const wrapper = rail(
      [
        { entry_id: "entry-1", word: "кућа", status: "pending" },
        { entry_id: "entry-2", word: "прозор", status: "done", detail_pending: true },
        { entry_id: "entry-3", word: "радити", status: "done" },
      ],
      "entry-3",
    );

    expect(wrapper.get('[data-testid="chip-entry-1"]').classes()).toContain("running");
    expect(wrapper.get('[data-testid="chip-entry-2"]').classes()).toContain("running");
    expect(wrapper.get('[data-testid="chip-entry-3"]').classes()).not.toContain("running");
  });

  // A failed entry is finished, not running.
  it("leaves a failed entry's chip still", () => {
    const wrapper = rail([
      { entry_id: "entry-1", word: "кућа", status: "error", error: "analysis_failed" },
    ]);

    expect(wrapper.get(".chip").classes()).not.toContain("running");
  });

  it("renders no strip at all when the language has nothing yet", () => {
    const wrapper = rail([], "");

    expect(wrapper.find(".chips").exists()).toBe(false);
  });

  it("scrolls the selected chip towards the middle when the selection moves", async () => {
    const wrapper = rail(
      [
        { entry_id: "entry-1", word: "кућа", status: "done" },
        { entry_id: "entry-2", word: "прозор", status: "done" },
      ],
      "entry-1",
    );
    const strip = wrapper.get(".chips").element;
    const scrolled = [];
    strip.scrollTo = (options) => scrolled.push(options);
    Object.defineProperty(strip, "clientWidth", { configurable: true, value: 300 });
    const chip = wrapper.get('[data-testid="chip-entry-2"]').element;
    Object.defineProperty(chip, "offsetLeft", { configurable: true, value: 400 });
    Object.defineProperty(chip, "offsetWidth", { configurable: true, value: 80 });

    await wrapper.setProps({ selectedId: "entry-2" });
    await wrapper.vm.$nextTick();

    expect(scrolled).toEqual([{ left: 290, behavior: "smooth" }]);
  });
});
