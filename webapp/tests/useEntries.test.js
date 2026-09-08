import { beforeEach, describe, expect, it, vi } from "vitest";

import { entries, upsertEntry } from "../src/composables/useEntries.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

beforeEach(async () => {
  await labelBehavior(EPIC.APPLICATION_PLATFORM, FEATURE.PWA_RESILIENCE, "Bounded history");
  entries.value = [];
  localStorage.clear();
});

function fill(count, status = "done") {
  for (let index = 0; index < count; index += 1) {
    upsertEntry({ entry_id: `entry-${index}`, word: `word-${index}`, status }, { newest: true });
  }
}

describe("useEntries", () => {
  it("merges an update into the entry it names and leaves the rest alone", () => {
    upsertEntry({ entry_id: "entry-1", word: "house", status: "pending" }, { newest: true });

    upsertEntry({ entry_id: "entry-1", status: "done", text: "дом" });

    expect(entries.value).toEqual([
      { entry_id: "entry-1", word: "house", status: "done", text: "дом" },
    ]);
  });

  it("keeps at most fifty entries, dropping the oldest", () => {
    fill(52);

    expect(entries.value).toHaveLength(50);
    expect(entries.value[0].entry_id).toBe("entry-51");
    expect(entries.value.at(-1).entry_id).toBe("entry-2");
  });

  it("never evicts an entry still waiting for its answer", () => {
    upsertEntry({ entry_id: "oldest", word: "waiting", status: "pending" }, { newest: true });
    fill(60);

    expect(entries.value).toHaveLength(50);
    expect(entries.value.at(-1).entry_id).toBe("oldest");
  });

  it("leaves a snapshot longer than the cap alone until the next insert", () => {
    fill(50);

    upsertEntry({ entry_id: "entry-0", text: "still here" });

    expect(entries.value).toHaveLength(50);
  });

  it("restores the full answer and paid detail after a module reload", async () => {
    upsertEntry({ entry_id: "saved", word: "кућа", text: "дом", detail_html: "detail", status: "done" });
    vi.resetModules();
    const restored = await import("../src/composables/useEntries.js");
    expect(restored.entries.value).toEqual(entries.value);
    restored.restoreEntries();
    expect(restored.entries.value).toEqual(entries.value);
  });

  it("trims a pending overflow when an answer finishes", async () => {
    vi.resetModules();
    const restored = await import("../src/composables/useEntries.js");
    for (let id = 0; id < 51; id += 1) {
      restored.upsertEntry({ entry_id: String(id), status: "pending" }, { newest: true });
    }
    expect(restored.entries.value).toHaveLength(51);
    restored.upsertEntry({ entry_id: "0", status: "done" });
    expect(restored.entries.value).toHaveLength(50);
    expect(restored.entries.value.some((entry) => entry.entry_id === "0")).toBe(false);
  });
});
