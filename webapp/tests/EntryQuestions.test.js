import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

import EntryCard from "../src/components/EntryCard.vue";
import { entries, upsertEntry } from "../src/composables/useEntries.js";
import { _resetForTest } from "../src/composables/useFollowUps.js";
import { locale } from "../src/i18n/index.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

const encoder = new TextEncoder();

function reply() {
  let controller;
  const body = new ReadableStream({
    start(opened) {
      controller = opened;
    },
  });
  return {
    response: { ok: true, status: 200, body, json: async () => ({}) },
    send(name, data = {}) {
      controller.enqueue(encoder.encode(`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`));
    },
    close() {
      controller.close();
    },
  };
}

function word(fields = {}) {
  return {
    entry_id: "e-1",
    word: "Schlüssel",
    lang: "de",
    shape: "unit",
    status: "done",
    text: "ключ",
    card_status: "added",
    ...fields,
  };
}

function shown(fields = {}) {
  upsertEntry(word(fields));
  return mount(EntryCard, { props: { entry: entries.value[0] } });
}

let fetchMock;

beforeEach(async () => {
  await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.ANSWER_DELIVERY, "Follow-up questions");
  entries.value = [];
  localStorage.clear();
  locale.value = "en";
  _resetForTest();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  locale.value = "en";
});

describe("the question field on an entry", () => {
  it.each([
    ["a carded word", {}],
    ["a lookup", { lookup_only: true, card_status: "lookup_only" }],
    ["a word whose card failed", { card_status: "failed" }],
  ])("stands under %s with nothing asked yet", (_name, fields) => {
    const wrapper = shown(fields);

    expect(wrapper.get(".ask-field").attributes("aria-label")).toBe("Ask about this entry");
    expect(wrapper.get(".ask-send").text()).toBe("Send");
    expect(wrapper.get(".ask-send").attributes("disabled")).toBeDefined();
    expect(wrapper.findAll(".turn")).toHaveLength(0);
  });

  it.each([
    ["running text", { shape: "text" }],
    ["an answer still coming", { status: "pending", shape: null }],
    ["a failed analysis", { status: "error", shape: null }],
  ])("is not offered on %s", (_name, fields) => {
    expect(shown(fields).find(".ask-field").exists()).toBe(false);
  });

  it("is named in Russian on a Russian page", () => {
    locale.value = "ru";
    const wrapper = shown();

    expect(wrapper.get(".ask-field").attributes("placeholder")).toBe("Спросить об этой записи");
    expect(wrapper.get(".ask-send").text()).toBe("Отправить");
  });

  it("keeps the draft with the entry and sends it on Enter", async () => {
    const answer = reply();
    fetchMock.mockResolvedValueOnce(answer.response);
    const wrapper = shown();

    await wrapper.get(".ask-field").setValue("What is <b>this</b>?");
    expect(entries.value[0].follow_up_draft).toBe("What is <b>this</b>?");
    await wrapper.get(".ask-field").trigger("keydown", { key: "Enter" });
    await wrapper.setProps({ entry: entries.value[0] });

    expect(wrapper.get(".turn-question").text()).toBe("What is <b>this</b>?");
    expect(wrapper.get(".turn-question").find("b").exists()).toBe(false);
    expect(wrapper.find(".turn-waiting").exists()).toBe(true);
    expect(wrapper.get(".ask-send").attributes("disabled")).toBeDefined();

    answer.send("delta", { text: "<i>Plain</i> text." });
    answer.send("done");
    answer.close();
    await flushPromises();
    await wrapper.setProps({ entry: entries.value[0] });

    expect(wrapper.get(".turn-answer").text()).toBe("<i>Plain</i> text.");
    expect(wrapper.get(".turn-answer").find("i").exists()).toBe(false);
    expect(wrapper.find(".turn-cut").exists()).toBe(false);
  });

  it("says a reply was cut off and offers Retry beside it", async () => {
    const wrapper = shown({
      follow_ups: [
        { id: "t-1", question: "Cut?", answer: "Half", state: "asking" },
        { id: "t-2", question: "Unsent?", answer: "", state: "cut", unsent: true },
        { id: "t-3", question: "Silent?", answer: "", state: "cut" },
      ],
    });

    const notes = wrapper.findAll(".turn-cut-note").map((note) => note.text());
    expect(notes).toEqual([
      "The reply was cut off.",
      "Not sent — the server could not be reached.",
      "No reply came.",
    ]);
    expect(wrapper.findAll(".turn-retry")).toHaveLength(3);

    const answer = reply();
    fetchMock.mockResolvedValueOnce(answer.response);
    await wrapper.findAll(".turn-retry")[0].trigger("click");
    answer.send("delta", { text: "Whole." });
    answer.send("done");
    answer.close();
    await flushPromises();
    await wrapper.setProps({ entry: entries.value[0] });

    expect(wrapper.findAll(".turn-question").map((item) => item.text())).toEqual([
      "Cut?",
      "Unsent?",
      "Silent?",
    ]);
    expect(wrapper.findAll(".turn-answer").map((item) => item.text())).toEqual(["Whole."]);
  });

  it("shows a refusal under the field and puts the question back in it", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ detail: "The question is too long." }),
    });
    const wrapper = shown();

    await wrapper.get(".ask-field").setValue("Long?");
    await wrapper.get("form.ask").trigger("submit");
    await flushPromises();
    await wrapper.setProps({ entry: entries.value[0] });

    expect(wrapper.get(".ask-refusal").text()).toBe("The question is too long.");
    expect(wrapper.get(".ask-field").element.value).toBe("Long?");
    expect(wrapper.findAll(".turn")).toHaveLength(0);
  });

  it("leaves a press on the field or a reply to typing and selection, not the swipe", async () => {
    const wrapper = shown({
      follow_ups: [{ id: "t-1", question: "Q?", answer: "A.", state: "done" }],
    });
    const deck = wrapper.get(".deck");

    for (const selector of [".ask-field", ".turn-answer", ".turn-question"]) {
      await wrapper.get(selector).trigger("pointerdown", { clientX: 200 });
      await deck.trigger("pointermove", { clientX: 100 });
      await deck.trigger("pointerup");
    }

    expect(wrapper.emitted("swipe")).toBeUndefined();
  });
});
