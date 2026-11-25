import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";

import { readCache } from "../src/api/cache.js";
import { entries, MAX_ENTRIES, upsertEntry } from "../src/composables/useEntries.js";
import {
  _resetForTest,
  ask,
  isAsking,
  refusals,
  retry,
  setDraft,
  turnState,
} from "../src/composables/useFollowUps.js";
import { locale } from "../src/i18n/index.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

const encoder = new TextEncoder();

// A reply the test writes event by event, as the server's stream delivers it.
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
    drop() {
      controller.error(new TypeError("network error"));
    },
  };
}

function refused(status, detail) {
  return { ok: false, status, json: async () => ({ detail }) };
}

function entry(fields = {}) {
  return {
    entry_id: "e-1",
    word: "Schlüssel",
    lang: "de",
    language: "Deutsch",
    shape: "unit",
    status: "done",
    text: "<b>Schlüssel</b> — ключ",
    context: "",
    card_status: "added",
    segment_kind: "senses",
    carded_sense: 0,
    segments: [
      { label: "Schlüssel", reason: "ключ" },
      { label: "Schlüssel", reason: "разгадка" },
    ],
    ...fields,
  };
}

function sent(call) {
  return JSON.parse(globalThis.fetch.mock.calls[call][1].body);
}

function stored(entryId = "e-1") {
  return readCache("history").data.find((item) => item.entry_id === entryId);
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
});

describe("follow-up questions", () => {
  it("shows the question at once, streams the reply under it and keeps both", async () => {
    upsertEntry(entry());
    const answer = reply();
    fetchMock.mockResolvedValueOnce(answer.response);
    setDraft("e-1", "  Why ключ?  ");

    const asking = ask("e-1");
    expect(entries.value[0].follow_ups).toEqual([
      expect.objectContaining({ question: "Why ключ?", answer: "", state: "asking" }),
    ]);
    expect(entries.value[0].follow_up_draft).toBe("");
    expect(isAsking(entries.value[0])).toBe(true);

    answer.send("delta", { text: "Because " });
    answer.send("delta", { text: "it opens." });
    await flushPromises();
    expect(entries.value[0].follow_ups[0].answer).toBe("Because it opens.");

    answer.send("done", { model: "pool", complete: true });
    answer.close();
    await asking;

    expect(stored().follow_ups).toEqual([
      expect.objectContaining({ question: "Why ключ?", answer: "Because it opens.", state: "done" }),
    ]);
    expect(isAsking(entries.value[0])).toBe(false);
  });

  it("sends what the reader sees on the entry, in the page's language", async () => {
    locale.value = "ru";
    upsertEntry(entry({ analysed_as: "Schlüssel", context: "Wo ist der Schlüssel?", detail_html: "<p>Art.</p>" }));
    const answer = reply();
    fetchMock.mockResolvedValueOnce(answer.response);
    setDraft("e-1", "Что значит второе?");

    const asking = ask("e-1");
    answer.send("done");
    answer.close();
    await asking;

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/words/e-1/ask");
    expect(init.headers["Accept-Language"]).toBe("ru");
    expect(sent(0)).toEqual({
      lang: "de",
      word: "Schlüssel",
      analysed_as: "Schlüssel",
      context: "Wo ist der Schlüssel?",
      analysis: "<b>Schlüssel</b> — ключ",
      // The carded sense has no chip once the card is made; a sense chip is its meaning.
      chips: [{ label: "разгадка", note: "" }],
      detail: "<p>Art.</p>",
      exchanges: [],
      question: "Что значит второе?",
    });
  });

  it("waits for a deeper article still being written before asking", async () => {
    upsertEntry(entry({ detail_pending: true, detail_html: "<p>Half</p>" }));
    const answer = reply();
    fetchMock.mockResolvedValueOnce(answer.response);
    setDraft("e-1", "And the article?");

    const asking = ask("e-1");
    await flushPromises();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(entries.value[0].follow_ups[0].state).toBe("asking");

    upsertEntry({ entry_id: "e-1", detail_pending: false, detail_html: "<p>Whole article</p>" });
    await flushPromises();
    expect(sent(0).detail).toBe("<p>Whole article</p>");
    answer.send("done");
    answer.close();
    await asking;
  });

  it("puts only completed replies into the next question's context", async () => {
    upsertEntry(
      entry({
        follow_ups: [
          { id: "t-1", question: "First?", answer: "First answer.", state: "done" },
          { id: "t-2", question: "Second?", answer: "Half an", state: "cut" },
        ],
      }),
    );
    const answer = reply();
    fetchMock.mockResolvedValueOnce(answer.response);
    setDraft("e-1", "Third?");

    const asking = ask("e-1");
    answer.send("done");
    answer.close();
    await asking;

    expect(sent(0).exchanges).toEqual([{ question: "First?", answer: "First answer." }]);
  });

  it("allows one question at a time on an entry", async () => {
    upsertEntry(entry());
    const answer = reply();
    fetchMock.mockResolvedValueOnce(answer.response);
    setDraft("e-1", "One?");
    const asking = ask("e-1");
    setDraft("e-1", "Two?");

    await ask("e-1");

    expect(entries.value[0].follow_ups).toHaveLength(1);
    expect(entries.value[0].follow_up_draft).toBe("Two?");
    answer.send("done");
    answer.close();
    await asking;
  });

  it("writes each chunk to the entry and turn that asked, whichever is on screen", async () => {
    upsertEntry(entry());
    upsertEntry(entry({ entry_id: "e-2", word: "Schloss" }));
    const first = reply();
    const second = reply();
    fetchMock.mockResolvedValueOnce(first.response).mockResolvedValueOnce(second.response);
    setDraft("e-1", "About Schlüssel?");
    setDraft("e-2", "About Schloss?");

    const one = ask("e-1");
    const two = ask("e-2");
    second.send("delta", { text: "lock" });
    first.send("delta", { text: "key" });
    for (const each of [first, second]) {
      each.send("done");
      each.close();
    }
    await Promise.all([one, two]);

    expect(stored("e-1").follow_ups[0].answer).toBe("key");
    expect(stored("e-2").follow_ups[0].answer).toBe("lock");
  });

  it("replaces the reply so far when the server says another model's answer won", async () => {
    upsertEntry(entry());
    const answer = reply();
    fetchMock.mockResolvedValueOnce(answer.response);
    setDraft("e-1", "Why?");

    const asking = ask("e-1");
    answer.send("delta", { text: "Lost half" });
    answer.send("reset");
    answer.send("delta", { text: "Whole answer." });
    answer.send("done");
    answer.close();
    await asking;

    expect(entries.value[0].follow_ups[0].answer).toBe("Whole answer.");
  });

  it("marks a reply cut off by a dropped connection and keeps what came", async () => {
    upsertEntry(entry());
    const answer = reply();
    fetchMock.mockResolvedValueOnce(answer.response);
    setDraft("e-1", "Why?");

    const asking = ask("e-1");
    answer.send("delta", { text: "Because" });
    await flushPromises();
    answer.drop();
    await asking;

    const [turn] = entries.value[0].follow_ups;
    expect(turn).toMatchObject({ question: "Why?", answer: "Because", state: "cut" });
    expect(turn.unsent).toBeFalsy();
  });

  it("marks a reply the server broke off, and one that ended without finishing", async () => {
    upsertEntry(entry());
    upsertEntry(entry({ entry_id: "e-2" }));
    const broken = reply();
    const silent = reply();
    fetchMock.mockResolvedValueOnce(broken.response).mockResolvedValueOnce(silent.response);
    setDraft("e-1", "One?");
    setDraft("e-2", "Two?");

    const one = ask("e-1");
    broken.send("delta", { text: "Part" });
    broken.send("error", { detail: "cut", retryable: true });
    broken.close();
    const two = ask("e-2");
    silent.close();
    await Promise.all([one, two]);

    expect(stored("e-1").follow_ups[0]).toMatchObject({ answer: "Part", state: "cut" });
    expect(stored("e-2").follow_ups[0]).toMatchObject({ answer: "", state: "cut" });
  });

  it("keeps a question sent with no connection, and retry sends it in the same place", async () => {
    upsertEntry(entry());
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    setDraft("e-1", "Offline?");

    await ask("e-1");

    const [turn] = entries.value[0].follow_ups;
    expect(turn).toMatchObject({ question: "Offline?", state: "cut", unsent: true });

    const answer = reply();
    fetchMock.mockResolvedValueOnce(answer.response);
    const retrying = retry("e-1", turn.id);
    answer.send("delta", { text: "Now." });
    answer.send("done");
    answer.close();
    await retrying;

    expect(stored().follow_ups).toEqual([
      expect.objectContaining({ id: turn.id, question: "Offline?", answer: "Now.", state: "done" }),
    ]);
    expect(stored().follow_ups[0].unsent).toBe(false);
  });

  it("shows a reply a reload interrupted as cut off, and retry replaces that turn", async () => {
    upsertEntry(
      entry({
        follow_ups: [
          { id: "t-1", question: "First?", answer: "First answer.", state: "done" },
          { id: "t-2", question: "Second?", answer: "Half", state: "asking" },
        ],
      }),
    );
    // A fresh page answers nothing yet: the stored turn was the previous page's.
    _resetForTest();
    const turn = entries.value[0].follow_ups[1];
    expect(turnState(turn)).toBe("cut");
    expect(isAsking(entries.value[0])).toBe(false);

    const answer = reply();
    fetchMock.mockResolvedValueOnce(answer.response);
    const retrying = retry("e-1", "t-2");
    expect(entries.value[0].follow_ups[1]).toMatchObject({ answer: "", state: "asking" });
    answer.send("delta", { text: "Second answer." });
    answer.send("done");
    answer.close();
    await retrying;

    expect(sent(0)).toMatchObject({
      question: "Second?",
      exchanges: [{ question: "First?", answer: "First answer." }],
    });
    expect(stored().follow_ups.map((item) => [item.question, item.answer, item.state])).toEqual([
      ["First?", "First answer.", "done"],
      ["Second?", "Second answer.", "done"],
    ]);
  });

  it("hands a refused question back to the field with the server's reason", async () => {
    upsertEntry(entry());
    fetchMock.mockResolvedValueOnce(refused(413, "Too much to send: 40000 of 32000."));
    setDraft("e-1", "A long one?");

    await ask("e-1");

    expect(entries.value[0].follow_ups).toEqual([]);
    expect(entries.value[0].follow_up_draft).toBe("A long one?");
    expect(refusals["e-1"]).toBe("Too much to send: 40000 of 32000.");
    // The refusal answers one request and is never stored with the entry.
    expect(JSON.stringify(stored())).not.toContain("Too much to send");
  });

  it("marks a pool that cannot answer as no reply, with the question kept", async () => {
    upsertEntry(entry());
    fetchMock.mockResolvedValueOnce(refused(503, "No model could answer."));
    setDraft("e-1", "Anyone?");

    await ask("e-1");

    expect(entries.value[0].follow_ups[0]).toMatchObject({
      question: "Anyone?",
      answer: "",
      state: "cut",
      unsent: false,
    });
  });

  it("drops the conversation with its entry when the history evicts it", () => {
    upsertEntry(
      entry({ follow_ups: [{ id: "t-1", question: "Q?", answer: "A.", state: "done" }] }),
    );
    for (let index = 0; index < MAX_ENTRIES; index += 1) {
      upsertEntry(entry({ entry_id: `n-${index}` }), { newest: true });
    }

    expect(stored("e-1")).toBeUndefined();
    expect(JSON.stringify(readCache("history").data)).not.toContain("Q?");
  });

  it("does not create an entry for a draft typed on one that is gone", () => {
    setDraft("gone", "Hello?");

    expect(entries.value).toEqual([]);
  });
});
