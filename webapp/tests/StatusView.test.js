import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

import { apiRequest } from "../src/api/_request.js";
import { serverReach, ServerUnreachable } from "../src/composables/useServerReach.js";
import StatusView from "../src/views/StatusView.vue";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

beforeEach(async () => {
  await labelBehavior(EPIC.APPLICATION_PLATFORM, FEATURE.CONFIGURATION_AND_LIFECYCLE, "Status view");
  apiRequest.mockReset();
  serverReach.value = { answeredAt: null, failure: null };
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function unreachable(kind, hostname = "echo-words-1.tail1234.ts.net") {
  vi.stubGlobal("location", { hostname });
  apiRequest.mockRejectedValue(new ServerUnreachable(kind));
  const wrapper = mount(StatusView);
  await flushPromises();
  return wrapper;
}

function checks(wrapper) {
  return wrapper.findAll("li").map((item) => item.attributes("data-testid"));
}

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

  it("makes the key help's own link followable instead of printing its markdown", async () => {
    apiRequest.mockResolvedValue({
      pool: {
        available: true,
        providers_usable: 1,
        providers_total: 1,
        degraded: false,
        missing_keys: [
          {
            api_key_ref: "GROQ_API_KEY",
            help: "Create a free API key at [groq](https://console.groq.com/keys) first",
          },
        ],
      },
      paid_calls: { today: 0, daily_cap: 10 },
      anki: { last_result: "ok", unsynced_changes: false, full_sync_required: false },
      languages: {},
    });
    const wrapper = mount(StatusView);
    await flushPromises();

    const link = wrapper.get("a[href='https://console.groq.com/keys']");
    expect(link.text()).toBe("groq");
    expect(link.attributes("rel")).toContain("noopener");
    expect(wrapper.text()).toContain("Create a free API key at groq first");
    expect(wrapper.text()).not.toContain("](");
  });

  it("asks for the status with a time limit, so a stopped server is not a minute's wait", async () => {
    await unreachable("no-answer");

    expect(apiRequest).toHaveBeenCalledWith("/api/status", { timeoutMs: 10_000 });
  });

  it("puts the stopped server first when the server did not answer at all", async () => {
    serverReach.value = { answeredAt: Date.UTC(2026, 9, 1, 9, 30), failure: null };

    const wrapper = await unreachable("no-answer");

    expect(wrapper.get("h2").text()).toBe("The server isn't answering.");
    expect(wrapper.text()).toContain("Last answered on this device:");
    expect(checks(wrapper)).toEqual(["check-vm", "check-internet"]);
    expect(wrapper.get('[data-testid="check-vm"]').text()).toContain("“echo-words-1” shows as online");
    expect(wrapper.get('[data-testid="check-vm"]').text()).toContain(
      "Oracle Cloud console, open Compute → Instances → the VM and press Start",
    );
    expect(wrapper.text()).not.toContain("Pay As You Go");
  });

  it("puts Tailscale on this device first when the server's name did not resolve", async () => {
    const wrapper = await unreachable("unreachable");

    expect(wrapper.get("h2").text()).toBe("Can't reach the server.");
    expect(wrapper.text()).toContain("It has not answered on this device yet.");
    expect(checks(wrapper)).toEqual(["check-tailscale", "check-internet", "check-vm"]);
  });

  it("sends the reader to the install agent when the VM answers for a stopped app", async () => {
    const wrapper = await unreachable("app-down");

    expect(wrapper.get("h2").text()).toBe("The server is on, but echo-words isn't running on it.");
    expect(checks(wrapper)).toEqual(["check-app"]);
    expect(wrapper.text()).toContain("uv run inv status");
  });

  it("leaves Tailscale and Oracle out for a server outside a tailnet", async () => {
    const wrapper = await unreachable("no-answer", "127.0.0.1");

    expect(checks(wrapper)).toEqual(["check-local"]);
    expect(wrapper.text()).toContain("The echo-words server at 127.0.0.1 is running.");
  });

  it("prints any other failure as before", async () => {
    apiRequest.mockRejectedValue(Object.assign(new Error("Internal Server Error"), { status: 500 }));
    const wrapper = mount(StatusView);
    await flushPromises();

    expect(wrapper.find('[data-testid="server-reach"]').exists()).toBe(false);
    expect(wrapper.get(".error").text()).toBe("Internal Server Error");
  });
});
