import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("../src/composables/useResendQueue.js", () => ({ flushQueue: vi.fn() }));
vi.mock("../src/views/AddView.vue", () => ({ default: { template: "<div />" } }));
vi.mock("../src/views/StatsView.vue", () => ({ default: { template: "<div />" } }));
vi.mock("../src/views/StatusView.vue", () => ({ default: { template: "<div />" } }));

import App from "../src/App.vue";
import { flushQueue } from "../src/composables/useResendQueue.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

afterEach(() => {
  vi.clearAllMocks();
});

describe("App", () => {
  it("flushes saved words on open and on each online event", async () => {
    await labelBehavior(EPIC.APPLICATION_PLATFORM, FEATURE.PWA_RESILIENCE, "Offline resend queue");
    const wrapper = mount(App);

    expect(flushQueue).toHaveBeenCalledTimes(1);
    window.dispatchEvent(new Event("online"));
    expect(flushQueue).toHaveBeenCalledTimes(2);

    wrapper.unmount();
    window.dispatchEvent(new Event("online"));
    expect(flushQueue).toHaveBeenCalledTimes(2);
  });
});
