import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("../src/composables/useResendQueue.js", () => ({ flushQueue: vi.fn() }));
vi.mock("../src/views/AddView.vue", () => ({
  default: {
    emits: ["navigate"],
    template: '<div id="add-view"><button id="to-languages" @click="$emit(\'navigate\', \'languages\')" /></div>',
  },
}));
vi.mock("../src/views/StatsView.vue", () => ({ default: { template: '<div id="stats-view" />' } }));
vi.mock("../src/views/StatusView.vue", () => ({ default: { template: '<div id="status-view" />' } }));
vi.mock("../src/views/LanguagesView.vue", () => ({
  default: {
    emits: ["back", "open"],
    template: '<div id="languages-view"><button id="open-sr" @click="$emit(\'open\', \'sr\')" /><button id="to-words" @click="$emit(\'back\')" /></div>',
  },
}));
vi.mock("../src/views/LanguageDetailView.vue", () => ({
  default: {
    props: ["code"],
    emits: ["back", "done"],
    template: '<div id="language-view">{{ code }}<button id="to-list" @click="$emit(\'back\')" /></div>',
  },
}));

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

  it("switches views from the icon navigation", async () => {
    await labelBehavior(EPIC.APPLICATION_PLATFORM, FEATURE.PWA_RESILIENCE, "Icon navigation");
    const wrapper = mount(App);

    expect(wrapper.find("#add-view").exists()).toBe(true);
    expect(wrapper.get('[data-testid="nav-add"]').attributes("aria-selected")).toBe("true");
    expect(wrapper.get('[data-testid="nav-add"]').text()).toBe("");

    await wrapper.get('[data-testid="nav-stats"]').trigger("click");
    expect(wrapper.find("#stats-view").exists()).toBe(true);
    expect(wrapper.get('[data-testid="nav-stats"]').attributes("aria-selected")).toBe("true");

    await wrapper.get('[data-testid="nav-status"]').trigger("click");
    expect(wrapper.find("#status-view").exists()).toBe(true);

    wrapper.unmount();
  });

  // The editor is reached from the words screen; the three tabs stay as they are,
  // and both of its screens belong to the words tab.
  it("opens the language editor from the words screen and comes back", async () => {
    await labelBehavior(
      EPIC.APPLICATION_PLATFORM,
      FEATURE.CONFIGURATION_AND_LIFECYCLE,
      "Language editor",
    );
    const wrapper = mount(App);

    await wrapper.get("#to-languages").trigger("click");
    expect(wrapper.find("#languages-view").exists()).toBe(true);
    expect(wrapper.get('[data-testid="nav-add"]').attributes("aria-selected")).toBe("true");

    await wrapper.get("#open-sr").trigger("click");
    expect(wrapper.get("#language-view").text()).toBe("sr");
    expect(wrapper.get('[data-testid="nav-add"]').attributes("aria-selected")).toBe("true");

    await wrapper.get("#to-list").trigger("click");
    expect(wrapper.find("#languages-view").exists()).toBe(true);

    await wrapper.get("#to-words").trigger("click");
    expect(wrapper.find("#add-view").exists()).toBe(true);

    wrapper.unmount();
  });

  it("shows the package version beside the app name", async () => {
    await labelBehavior(EPIC.APPLICATION_PLATFORM, FEATURE.HEALTH_AND_DEPLOYMENT, "Version in the header");
    const wrapper = mount(App);

    // The version is injected at build time from src/echo_words/__about__.py;
    // a semver match proves that file was read rather than the "dev" fallback.
    expect(wrapper.get(".header-version").text()).toMatch(/^v\d+\.\d+\.\d+$/u);

    wrapper.unmount();
  });
});
