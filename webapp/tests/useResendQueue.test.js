import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

import { apiRequest } from "../src/api/_request.js";
import {
  _resetForTest,
  enqueueWord,
  flushQueue,
  queuedWords,
} from "../src/composables/useResendQueue.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

const first = { word: "one", lang: "en", lookup_only: false };
const second = { word: "two", lang: "en", lookup_only: true };

beforeEach(async () => {
  await labelBehavior(EPIC.APPLICATION_PLATFORM, FEATURE.PWA_RESILIENCE, "Offline resend queue");
  localStorage.clear();
  apiRequest.mockReset();
  _resetForTest();
});

describe("resend queue", () => {
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

  it("keeps a conflicting request-id response for fail-closed inspection", async () => {
    enqueueWord(first);
    enqueueWord(second);
    apiRequest.mockRejectedValueOnce(Object.assign(new Error("conflict"), { status: 409 }));

    await flushQueue();

    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(queuedWords.value).toHaveLength(2);
  });
});
