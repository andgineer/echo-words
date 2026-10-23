import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, ref } from "vue";

vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

import { apiRequest } from "../src/api/_request.js";
import { entries } from "../src/composables/useEntries.js";
import {
  _resetForTest,
  dismissRefusal,
  enqueueWord,
  flushQueue,
  preview,
  queuedWords,
  refusedWords,
  resendWhileWaiting,
  useResendQueue,
} from "../src/composables/useResendQueue.js";
import {
  _resetForTest as resetReach,
  noteAnswer,
  noteFailure,
  ServerUnreachable,
} from "../src/composables/useServerReach.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

const first = { word: "one", lang: "en", lookup_only: false };
const second = { word: "two", lang: "en", lookup_only: true };

beforeEach(async () => {
  await labelBehavior(EPIC.APPLICATION_PLATFORM, FEATURE.PWA_RESILIENCE, "Offline resend queue");
  localStorage.clear();
  entries.value = [];
  apiRequest.mockReset();
  _resetForTest();
  resetReach();
});

function posts() {
  return apiRequest.mock.calls.filter(([path]) => path === "/api/words").length;
}

// What a real request does on its way: the server's answer is noted before it is read.
function answeredWith(entryId) {
  return async () => {
    noteAnswer();
    return { entry_id: entryId };
  };
}

async function unreachable() {
  throw noteFailure("unreachable");
}

describe("resend queue", () => {
  it("resends under the same time limit as a fresh submission", async () => {
    enqueueWord(first);
    apiRequest.mockResolvedValue({ entry_id: "accepted" });

    await flushQueue();

    expect(apiRequest).toHaveBeenCalledWith("/api/words", {
      method: "POST",
      body: { ...first, request_id: expect.any(String) },
      timeoutMs: 15_000,
    });
  });

  it("keeps a returned acceptance even if the stream has not connected", async () => {
    enqueueWord(first);
    apiRequest.mockResolvedValue({ entry_id: "accepted", word: "one", lookup_only: false });
    await flushQueue();
    expect(entries.value[0]).toMatchObject({ entry_id: "accepted", word: "one", lang: "en", status: "pending" });
  });

  it("does not turn an already streamed answer back into a pending job", async () => {
    entries.value = [{ entry_id: "accepted", text: "answer", status: "done" }];
    enqueueWord(first);
    apiRequest.mockResolvedValue({ entry_id: "accepted" });
    await flushQueue();
    expect(entries.value[0]).toMatchObject({ text: "answer", status: "done" });
  });

  it("records that a queued word asked for the target reading", async () => {
    enqueueWord({ word: "!город", lang: "sr", lookup_only: false });
    apiRequest.mockResolvedValue({
      entry_id: "accepted",
      word: "город",
      lookup_only: false,
      reverse: "forced",
    });

    await flushQueue();

    // Without it a queued `!город` that fails would retry as a word of the tab.
    expect(entries.value[0]).toMatchObject({
      word: "город",
      requested_reverse: "forced",
      status: "pending",
    });
  });

  it("keeps the word a lookup found when the queued receipt is read after it", async () => {
    entries.value = [
      {
        entry_id: "accepted",
        word: "grad",
        typed_word: "город",
        context: "Ovo je lep grad.",
        requested_shape: "unit",
        requested_reverse: null,
        lang: "sr",
        status: "pending",
      },
    ];
    enqueueWord({ word: "!город", lang: "sr", lookup_only: false });
    apiRequest.mockResolvedValue({
      entry_id: "accepted",
      word: "город",
      lookup_only: false,
      reverse: "forced",
    });

    await flushQueue();

    expect(entries.value[0]).toMatchObject({
      word: "grad",
      typed_word: "город",
      context: "Ovo je lep grad.",
      requested_shape: "unit",
      requested_reverse: null,
    });
  });

  it("re-sends saved words in order and removes successful items", async () => {
    enqueueWord(first);
    enqueueWord(second);
    apiRequest.mockResolvedValue({ entry_id: "accepted" });

    await flushQueue();

    const sent = apiRequest.mock.calls.map(([, options]) => options.body);
    expect(sent).toEqual([
      { ...first, request_id: expect.any(String) },
      { ...second, request_id: expect.any(String) },
    ]);
    expect(sent[0].request_id).not.toBe(sent[1].request_id);
    expect(queuedWords.value).toEqual([]);
    expect(JSON.parse(localStorage.getItem("echo-words-resend-queue"))).toEqual([]);
  });

  it("stops on the first failure and keeps it and the remainder", async () => {
    enqueueWord(first);
    enqueueWord(second);
    apiRequest.mockRejectedValue(new TypeError("offline"));

    await flushQueue();

    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(queuedWords.value.map((item) => item.body)).toEqual([
      { ...first, request_id: expect.any(String) },
      { ...second, request_id: expect.any(String) },
    ]);
  });

  it("retries after an accepted response is lost and drops the next acceptance", async () => {
    enqueueWord(first);
    apiRequest
      .mockRejectedValueOnce(new TypeError("response lost"))
      .mockResolvedValueOnce({ entry_id: "accepted-again" });

    const persistedId = JSON.parse(localStorage.getItem("echo-words-resend-queue"))[0].body
      .request_id;
    _resetForTest();

    await flushQueue();
    expect(queuedWords.value.map((item) => item.body)).toEqual([
      { ...first, request_id: persistedId },
    ]);

    await flushQueue();
    expect(apiRequest).toHaveBeenCalledTimes(2);
    expect(apiRequest.mock.calls[0][1].body.request_id).toBe(persistedId);
    expect(apiRequest.mock.calls[1][1].body.request_id).toBe(persistedId);
    expect(queuedWords.value).toEqual([]);
  });

  it.each([400, 409, 422])(
    "takes a word the server refuses (%s) off the queue, keeps why, and sends the rest",
    async (status) => {
      enqueueWord(first);
      enqueueWord(second);
      apiRequest
        .mockRejectedValueOnce(Object.assign(new Error("“English” needs the Latin script."), { status }))
        .mockResolvedValueOnce({ entry_id: "accepted" });

      expect(await flushQueue()).toBeNull();

      expect(apiRequest).toHaveBeenCalledTimes(2);
      expect(queuedWords.value).toEqual([]);
      expect(refusedWords.value).toEqual([
        { word: "one", reason: "“English” needs the Latin script." },
      ]);
      expect(JSON.parse(localStorage.getItem("echo-words-resend-refused"))).toEqual(
        refusedWords.value,
      );
    },
  );

  it.each([
    ["a server out of reach", new ServerUnreachable("unreachable")],
    ["a server error", Object.assign(new Error("Internal Server Error"), { status: 500 })],
  ])("keeps a word and what follows it on %s, and settles on that failure", async (_, error) => {
    enqueueWord(first);
    enqueueWord(second);
    apiRequest.mockRejectedValueOnce(error);

    expect(await flushQueue()).toBe(error);

    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(queuedWords.value).toHaveLength(2);
    expect(refusedWords.value).toEqual([]);
  });

  it("sends what is queued after a flush that found nothing to send", async () => {
    expect(await flushQueue()).toBeNull();
    enqueueWord(first);
    apiRequest.mockResolvedValue({ entry_id: "accepted" });

    expect(await flushQueue()).toBeNull();

    expect(posts()).toBe(1);
    expect(queuedWords.value).toEqual([]);
  });

  it("hands a flush asked for while one runs that same one, so no word goes twice", async () => {
    enqueueWord(first);
    enqueueWord(second);
    let release;
    apiRequest
      .mockImplementationOnce(() => new Promise((resolve) => (release = resolve)))
      .mockResolvedValueOnce({ entry_id: "second" });

    const running = flushQueue();
    expect(flushQueue()).toBe(running);
    await vi.waitFor(() => expect(apiRequest).toHaveBeenCalledTimes(1));
    const asked = flushQueue();
    release({ entry_id: "first" });

    expect(asked).toBe(running);
    expect(await asked).toBeNull();
    expect(apiRequest).toHaveBeenCalledTimes(2);
    expect(queuedWords.value).toEqual([]);
  });
});

describe("resend while words wait", () => {
  let scope;
  const visible = ref(true);

  function install() {
    scope = effectScope();
    scope.run(() => resendWhileWaiting(visible));
  }

  beforeEach(() => {
    visible.value = true;
    vi.useFakeTimers();
  });

  afterEach(() => {
    scope?.stop();
    scope = null;
    vi.useRealTimers();
  });

  it("sends the waiting words as soon as any request is answered", async () => {
    install();
    enqueueWord(first);
    apiRequest.mockImplementation(answeredWith("accepted"));

    noteAnswer();
    await vi.advanceTimersByTimeAsync(0);

    expect(posts()).toBe(1);
    expect(queuedWords.value).toEqual([]);
  });

  it("asks nothing of an answer while no word waits, nor of a failure while one does", async () => {
    install();
    noteAnswer();
    enqueueWord(first);
    noteFailure("unreachable");
    await vi.advanceTimersByTimeAsync(0);

    expect(apiRequest).not.toHaveBeenCalled();
  });

  it("starts no other flush on the answers its own sends get", async () => {
    install();
    enqueueWord(first);
    enqueueWord(second);
    apiRequest.mockImplementation(answeredWith("accepted"));

    noteAnswer();
    await flushQueue();
    await vi.advanceTimersByTimeAsync(0);

    const sent = apiRequest.mock.calls.map(([, options]) => options.body.word);
    expect(sent).toEqual(["one", "two"]);
    expect(queuedWords.value).toEqual([]);
  });

  it("starts no other flush on the answer that refuses a word", async () => {
    install();
    enqueueWord(first);
    apiRequest.mockImplementation(async () => {
      noteAnswer();
      throw Object.assign(new Error("conflict"), { status: 409 });
    });

    noteAnswer();
    await flushQueue();
    await vi.advanceTimersByTimeAsync(0);

    expect(posts()).toBe(1);
    expect(refusedWords.value).toEqual([{ word: "one", reason: "conflict" }]);
  });

  it("asks again every 30 seconds while a word waits, and sends it on the first answer", async () => {
    install();
    apiRequest.mockImplementation(unreachable);
    enqueueWord(first);
    await nextTick();

    await vi.advanceTimersByTimeAsync(29_999);
    expect(posts()).toBe(0);
    await vi.advanceTimersByTimeAsync(1);
    expect(posts()).toBe(1);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(posts()).toBe(2);
    expect(queuedWords.value).toHaveLength(1);

    apiRequest.mockImplementation(answeredWith("accepted"));
    await vi.advanceTimersByTimeAsync(30_000);
    expect(posts()).toBe(3);
    expect(queuedWords.value).toEqual([]);

    await vi.advanceTimersByTimeAsync(120_000);
    expect(posts()).toBe(3);
  });

  it("never asks while the page is hidden, and asks again once it is back on screen", async () => {
    install();
    apiRequest.mockImplementation(unreachable);
    enqueueWord(first);
    await nextTick();
    visible.value = false;
    await nextTick();

    await vi.advanceTimersByTimeAsync(120_000);
    expect(posts()).toBe(0);

    visible.value = true;
    await nextTick();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(posts()).toBe(1);
  });

  it("never overlaps one check with the next while the server keeps it waiting", async () => {
    install();
    let release;
    apiRequest.mockImplementation(() => new Promise((resolve) => (release = resolve)));
    enqueueWord(first);
    await nextTick();

    await vi.advanceTimersByTimeAsync(120_000);
    expect(posts()).toBe(1);

    release({ entry_id: "accepted" });
    await vi.advanceTimersByTimeAsync(0);
    expect(queuedWords.value).toEqual([]);
  });

  it("stops asking once the app is gone", async () => {
    install();
    apiRequest.mockImplementation(unreachable);
    enqueueWord(first);
    await nextTick();
    scope.stop();

    noteAnswer();
    await vi.advanceTimersByTimeAsync(120_000);
    expect(posts()).toBe(0);
  });
});

describe("refused words", () => {
  const LATIN = "“English” needs the Latin script.";
  const met = [
    { word: "слово", reason: LATIN },
    { word: "дом", reason: LATIN },
    { word: "слово", reason: LATIN },
  ];

  it("takes away only the refusal dismissed, and storage forgets it too", () => {
    localStorage.setItem("echo-words-resend-refused", JSON.stringify(met));
    useResendQueue();

    dismissRefusal(1);

    expect(refusedWords.value).toEqual([met[0], met[2]]);
    expect(JSON.parse(localStorage.getItem("echo-words-resend-refused"))).toEqual([met[0], met[2]]);
    _resetForTest();
    useResendQueue();
    expect(refusedWords.value).toEqual([met[0], met[2]]);
  });
});

describe("a submission's preview", () => {
  it("leaves a word that fits untouched", () => {
    expect(preview("ledig")).toBe("ledig");
    expect(preview("Bundesverfassung")).toBe("Bundesverfassung");
  });

  it("cuts a passage to its first sixteen characters, without a space before the dots", () => {
    expect(preview("Er steht jeden Morgen um sechs auf.")).toBe("Er steht jeden M…");
    expect(preview("Wir gehen heute nach Hause.")).toBe("Wir gehen heute…");
  });

  it("never splits a character written with more than one code point", () => {
    const accented = `${"x".repeat(15)}e\u0301tc`;
    expect(preview(accented)).toBe(`${"x".repeat(15)}e\u0301…`);
    const waving = `${"x".repeat(15)}👋🏽 hello`;
    expect(preview(waving)).toBe(`${"x".repeat(15)}👋🏽…`);
  });
});
