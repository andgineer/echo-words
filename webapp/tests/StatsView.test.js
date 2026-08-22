import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

import { apiRequest } from "../src/api/_request.js";
import StatsView from "../src/views/StatsView.vue";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

beforeEach(async () => {
  await labelBehavior(EPIC.ANKI_CARDS, FEATURE.STATS_AND_UNDO, "Statistics view");
  apiRequest.mockReset();
});

describe("StatsView", () => {
  it("labels durable note counts separately from startup counters", async () => {
    apiRequest.mockResolvedValue({
      languages: {
        en: {
          name: "English",
          today: 2,
          last_7_days: 5,
          all_time: 10,
          duplicates: 3,
          lookup_only: 1,
        },
      },
    });
    const wrapper = mount(StatsView);
    await flushPromises();

    expect(wrapper.text()).toContain("Today: 2");
    expect(wrapper.text()).toContain("All time: 10");
    expect(wrapper.text()).toContain("Since startup: 3 duplicates, 1 without a card");
  });
});
