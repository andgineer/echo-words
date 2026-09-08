import { beforeEach, expect, it, vi } from "vitest";
import { apiRequest } from "../src/api/_request.js";

vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

import { entries, replaceEntries } from "../src/composables/useEntries.js";
import { useEventStream } from "../src/composables/useEventStream.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

class FakeEventSource {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.listeners = new Map();
    this.closed = false;
    FakeEventSource.instances.push(this);
  }

  addEventListener(name, callback) {
    const callbacks = this.listeners.get(name) || [];
    callbacks.push(callback);
    this.listeners.set(name, callbacks);
  }

  emit(name, data = null) {
    const event = data === null ? {} : { data: JSON.stringify(data) };
    for (const callback of this.listeners.get(name) || []) callback(event);
  }

  close() {
    this.closed = true;
  }
}

beforeEach(async () => {
  await labelBehavior(EPIC.APPLICATION_PLATFORM, FEATURE.ANSWER_DELIVERY, "SSE recovery");
  entries.value = [];
  localStorage.clear();
  apiRequest.mockReset();
  FakeEventSource.instances = [];
});

it("replaces accumulated text when an update arrives", () => {
  entries.value = [{ entry_id: "one", text: "old" }];
  const stream = useEventStream({ EventSourceClass: FakeEventSource });
  stream.start();
  FakeEventSource.instances[0].emit("update", { entry_id: "one", text: "whole answer" });

  expect(entries.value[0].text).toBe("whole answer");
});

it("keeps deeper analysis in its own appended block", () => {
  entries.value = [{ entry_id: "one", text: "short answer" }];
  const stream = useEventStream({ EventSourceClass: FakeEventSource });
  stream.start();
  FakeEventSource.instances[0].emit("detail", { entry_id: "one", text: "deep answer" });

  expect(entries.value[0].text).toBe("short answer");
  expect(entries.value[0].detail_html).toBe("deep answer");
});

it("keeps the paid call marked as running until its last piece has arrived", () => {
  entries.value = [{ entry_id: "one", text: "short answer", detail_pending: true }];
  const stream = useEventStream({ EventSourceClass: FakeEventSource });
  stream.start();
  const source = FakeEventSource.instances[0];

  source.emit("detail", { entry_id: "one", text: "half an", streaming: true });
  expect(entries.value[0]).toMatchObject({ detail_html: "half an", detail_pending: true });

  source.emit("detail", { entry_id: "one", text: "half an article" });
  expect(entries.value[0]).toMatchObject({
    detail_html: "half an article",
    detail_pending: false,
  });
});

it("starts with an empty history without downloading server entries", async () => {
  apiRequest.mockResolvedValue([]);
  const stream = useEventStream({ EventSourceClass: FakeEventSource });
  stream.start();

  FakeEventSource.instances.at(-1).emit("open");

  await stream.refresh();
  expect(apiRequest).not.toHaveBeenCalled();
  expect(entries.value).toEqual([]);
});

it("does not create incomplete history from work that began before this device connected", () => {
  useEventStream({ EventSourceClass: FakeEventSource }).start();
  FakeEventSource.instances[0].emit("update", { entry_id: "unknown", text: "half" });
  FakeEventSource.instances[0].emit("done", { entry_id: "unknown", text: "finished" });
  expect(entries.value).toEqual([]);
});

it("clears deeper analysis when a correction switch resets the entry", () => {
  entries.value = [{
    entry_id: "one",
    text: "old",
    detail_html: "old detail",
    shape: "unit",
    segment_kind: "senses",
    carded_sense: 0,
    segments: [{ label: "word", context: "sentence" }],
    card_status: "added",
    card_kinds: ["Recognition"],
  }];
  const source = new FakeEventSource();
  useEventStream({ EventSourceClass: class { constructor() { return source; } } }).start();

  source.emit("reset", { entry_id: "one", detail_html: "" });

  expect(entries.value[0].detail_html).toBe("");
  expect(entries.value[0]).toMatchObject({
    shape: null,
    segment_kind: null,
    carded_sense: null,
    segments: [],
    card_status: null,
    card_kinds: [],
  });
});

it("surfaces a queued control refusal on its entry", () => {
  entries.value = [{ entry_id: "one", text: "kept answer", status: "done" }];
  const stream = useEventStream({ EventSourceClass: FakeEventSource });
  stream.start();
  FakeEventSource.instances[0].emit("control_error", {
    entry_id: "one",
    message: "the daily paid-call cap is spent",
  });

  expect(entries.value[0]).toMatchObject({
    text: "kept answer",
    status: "done",
    control_error: "the daily paid-call cap is spent",
  });
});

it("keeps finished local entries without network calls on reconnect", async () => {
  replaceEntries([{ entry_id: "one", text: "current", status: "done" }]);
  const stream = useEventStream({ EventSourceClass: FakeEventSource });
  stream.start();
  const source = FakeEventSource.instances[0];

  source.emit("open");
  await stream.refresh();
  source.emit("open");
  await stream.refresh();
  expect(apiRequest).not.toHaveBeenCalled();
  expect(entries.value).toEqual([{ entry_id: "one", text: "current", status: "done" }]);
});

it("recovers only known unfinished entries and replays newer live events", async () => {
  replaceEntries([
    { entry_id: "pending", status: "pending", text: "partial" },
    { entry_id: "finished", status: "done", text: "kept" },
  ]);
  let resolveEntry;
  const fetchEntry = vi.fn(() => new Promise((resolve) => { resolveEntry = resolve; }));
  const stream = useEventStream({ EventSourceClass: FakeEventSource, fetchEntry });
  stream.start();
  const refreshing = stream.refresh();
  FakeEventSource.instances[0].emit("done", { entry_id: "pending", text: "finished live" });
  resolveEntry({ entry_id: "pending", status: "pending", text: "stale" });
  await refreshing;
  expect(fetchEntry).toHaveBeenCalledTimes(1);
  expect(fetchEntry).toHaveBeenCalledWith("pending");
  expect(entries.value[0]).toMatchObject({ text: "finished live", status: "done" });
  expect(entries.value[1].text).toBe("kept");
});

it("ends a spinner when the server no longer has the pending entry", async () => {
  replaceEntries([{ entry_id: "lost", status: "pending" }]);
  const fetchEntry = vi.fn().mockRejectedValue(Object.assign(new Error("expired"), { status: 410 }));
  await useEventStream({ fetchEntry }).refresh();
  expect(entries.value[0]).toMatchObject({ status: "error", error: "analysis_failed" });
});

it("keeps a cached answer on a network failure", async () => {
  replaceEntries([{ entry_id: "kept", status: "pending", text: "partial" }]);
  const fetchEntry = vi.fn().mockRejectedValue(new Error("offline"));
  await expect(useEventStream({ fetchEntry }).refresh()).rejects.toThrow("offline");
  expect(entries.value[0]).toMatchObject({ text: "partial", status: "pending" });
});

it("replays live events after a stale reconnect snapshot", async () => {
  replaceEntries([{ entry_id: "one", status: "pending", text: "old" }]);
  let resolveRecent;
  const fetchEntry = vi.fn(() => new Promise((resolve) => {
    resolveRecent = resolve;
  }));
  const stream = useEventStream({ EventSourceClass: FakeEventSource, fetchEntry });
  stream.start();
  const source = FakeEventSource.instances[0];

  source.emit("open");
  source.emit("update", { entry_id: "one", text: "new live text" });
  resolveRecent({ entry_id: "one", text: "stale snapshot" });
  await vi.waitFor(() => expect(entries.value[0]?.text).toBe("new live text"));
});
