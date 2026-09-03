import { beforeEach, describe, expect, it } from "vitest";

import { entries, upsertEntry } from "../src/composables/useEntries.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

beforeEach(async () => {
  await labelBehavior(EPIC.APPLICATION_PLATFORM, FEATURE.PWA_RESILIENCE, "Bounded history");
  entries.value = [];
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

  // The server bounds its own history the same way, but the browser only re-syncs to
  // it on a stream reconnect: a tab left open for weeks would keep everything.
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
});
