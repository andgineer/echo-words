import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

import { apiRequest } from "../src/api/_request.js";
import StatusView from "../src/views/StatusView.vue";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

beforeEach(async () => {
  await labelBehavior(EPIC.APPLICATION_PLATFORM, FEATURE.CONFIGURATION_AND_LIFECYCLE, "Status view");
  apiRequest.mockReset();
});

describe("StatusView", () => {
  it("renders degraded pool, unsynced changes and full-sync warning", async () => {
    apiRequest.mockResolvedValue({
      pool: {
        available: true,
        providers_usable: 1,
        providers_total: 2,
        degraded: true,
        missing_keys: [{ api_key_ref: "FREE_KEY", help: "get a free key" }],
        direct_missing_keys: [{ api_key_ref: "PAID_KEY", help: "get a paid key" }],
      },
      paid_calls: { today: 4, daily_cap: 10 },
      anki: {
        last_result: "full-sync-required",
        unsynced_changes: true,
        full_sync_required: true,
        last_sync_at: "2026-08-19T10:00:00Z",
        error: "sync failed",
      },
      languages: {
        en: {
          name: "English",
          deck: "English::Vocabulary",
          paid_alias: "gpt-fast",
          paid_available_today: false,
          paid_refusal: "the paid model is missing PAID_KEY",
          last_call: {
            model: "free-flash",
            ok: false,
            at: "2026-08-19T09:30:00Z",
            error: "timeout",
          },
        },
      },
    });
    const wrapper = mount(StatusView);
    await flushPromises();

    expect(wrapper.text()).toContain("LLM: 1/2");
    expect(wrapper.text()).toContain("limited fallback");
    expect(wrapper.text()).toContain("unsynced changes");
    expect(wrapper.text()).toContain("A manual one-way Anki sync is required");
    expect(wrapper.text()).toContain("FREE_KEY — get a free key");
    expect(wrapper.text()).toContain("PAID_KEY — get a paid key");
    expect(wrapper.text()).toContain("gpt-fast");
    expect(wrapper.text()).toContain("unavailable: the paid model is missing PAID_KEY");
    expect(wrapper.text()).toContain("Last call: failed · free-flash");
    expect(wrapper.text()).toContain("timeout");
    expect(wrapper.text()).toContain("Sync error: sync failed");
    expect(wrapper.text()).toContain("Last sync:");
  });
});
