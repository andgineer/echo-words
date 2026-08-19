import { beforeEach, expect, it, vi } from "vitest";

import { entries } from "../src/composables/useEntries.js";
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
  FakeEventSource.instances = [];
});

it("replaces accumulated text when an update arrives", () => {
  entries.value = [{ entry_id: "one", text: "old" }];
  const stream = useEventStream({ EventSourceClass: FakeEventSource, fetchRecent: vi.fn() });
  stream.start();
  FakeEventSource.instances[0].emit("update", { entry_id: "one", text: "whole answer" });

  expect(entries.value[0].text).toBe("whole answer");
});

it("refetches recent entries on the initial open and every reconnect", async () => {
  const fetchRecent = vi.fn().mockResolvedValue([{ entry_id: "one", text: "current" }]);
  const stream = useEventStream({ EventSourceClass: FakeEventSource, fetchRecent });
  stream.start();
  const source = FakeEventSource.instances[0];

  source.emit("open");
  await vi.waitFor(() => expect(fetchRecent).toHaveBeenCalledTimes(1));
  source.emit("open");
  await vi.waitFor(() => expect(fetchRecent).toHaveBeenCalledTimes(2));
  expect(entries.value).toEqual([{ entry_id: "one", text: "current" }]);
});

it("replays live events after a stale reconnect snapshot", async () => {
  let resolveRecent;
  const fetchRecent = vi.fn(() => new Promise((resolve) => {
    resolveRecent = resolve;
  }));
  const stream = useEventStream({ EventSourceClass: FakeEventSource, fetchRecent });
  stream.start();
  const source = FakeEventSource.instances[0];

  source.emit("open");
  source.emit("update", { entry_id: "one", text: "new live text" });
  resolveRecent([{ entry_id: "one", text: "stale snapshot" }]);
  await vi.waitFor(() => expect(entries.value[0]?.text).toBe("new live text"));
});
