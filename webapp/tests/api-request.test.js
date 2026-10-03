import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../src/api/_request.js";
import { serverReach } from "../src/composables/useServerReach.js";
import { locale } from "../src/i18n/index.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

beforeEach(async () => {
  await labelBehavior(
    EPIC.APPLICATION_PLATFORM,
    FEATURE.API_CLIENT,
    "Request and response handling",
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  locale.value = "en";
  serverReach.value = { answeredAt: null, failure: null };
  localStorage.clear();
});

function mockFetch(status, body, contentLength = null) {
  const fetch = vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name) => (name === "content-length" ? contentLength : null) },
    json: async () => body,
  }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("apiRequest", () => {
  it("returns parsed JSON for a successful request", async () => {
    mockFetch(200, { code: "en" });

    await expect(apiRequest("/api/languages")).resolves.toEqual({ code: "en" });
  });

  it("serializes a JSON body and content type", async () => {
    const fetch = mockFetch(200, { entry_id: "entry-1" });

    await apiRequest("/api/words", { method: "POST", body: { word: "receive" } });

    expect(fetch).toHaveBeenCalledWith("/api/words", {
      method: "POST",
      headers: { "Accept-Language": "en", "Content-Type": "application/json" },
      body: JSON.stringify({ word: "receive" }),
    });
  });

  it("asks the backend for hints in the interface language", async () => {
    const fetch = mockFetch(200, []);
    locale.value = "ru";

    await apiRequest("/api/languages");

    expect(fetch).toHaveBeenCalledWith("/api/languages", {
      method: "GET",
      headers: { "Accept-Language": "ru" },
    });
  });

  it.each([
    [204, null],
    [200, "0"],
  ])("returns null for an empty response (%s)", async (status, contentLength) => {
    mockFetch(status, undefined, contentLength);

    await expect(apiRequest("/api/empty")).resolves.toBeNull();
  });

  it("uses a string detail from the backend", async () => {
    mockFetch(400, { detail: "Enter a word." });

    await expect(apiRequest("/api/words")).rejects.toMatchObject({
      message: "Enter a word.",
      status: 400,
    });
  });

  it("extracts the first Pydantic validation message", async () => {
    mockFetch(422, { detail: [{ msg: "String should have at most 200 characters" }] });

    await expect(apiRequest("/api/words")).rejects.toMatchObject({
      message: "String should have at most 200 characters",
      status: 422,
    });
  });

  it("falls back to the HTTP status when the error body is unusable", async () => {
    const fetch = vi.fn(async () => ({
      ok: false,
      status: 503,
      headers: { get: () => null },
      json: async () => {
        throw new Error("not JSON");
      },
    }));
    vi.stubGlobal("fetch", fetch);

    await expect(apiRequest("/api/words")).rejects.toMatchObject({
      message: "HTTP 503",
      status: 503,
    });
  });

  it("does not attach a time limit nobody asked for", async () => {
    const fetch = mockFetch(200, []);

    await apiRequest("/api/languages");

    expect(fetch.mock.calls[0][1].signal).toBeUndefined();
  });
});

describe("apiRequest when the server does not answer", () => {
  function hangingFetch() {
    const fetch = vi.fn(
      (path, init) =>
        new Promise((resolve, reject) => {
          init.signal.addEventListener("abort", () =>
            reject(new DOMException("The operation was aborted.", "AbortError")),
          );
        }),
    );
    vi.stubGlobal("fetch", fetch);
    return fetch;
  }

  function failingFetch(error) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw error;
      }),
    );
  }

  it("calls a request that outlives its time limit a server that does not answer", async () => {
    vi.useFakeTimers();
    hangingFetch();

    const request = apiRequest("/api/words", { method: "POST", body: {}, timeoutMs: 15_000 });
    const settled = expect(request).rejects.toMatchObject({
      name: "ServerUnreachable",
      kind: "no-answer",
      message: "The server isn't answering.",
    });
    await vi.advanceTimersByTimeAsync(14_999);
    expect(serverReach.value.failure).toBeNull();
    await vi.advanceTimersByTimeAsync(1);

    await settled;
    expect(serverReach.value.failure.kind).toBe("no-answer");
  });

  it("tells a device with no network from a server it cannot reach", async () => {
    failingFetch(new TypeError("Load failed"));
    vi.stubGlobal("navigator", { onLine: true });
    await expect(apiRequest("/api/status")).rejects.toMatchObject({ kind: "unreachable" });

    vi.stubGlobal("navigator", { onLine: false });
    await expect(apiRequest("/api/status")).rejects.toMatchObject({ kind: "offline" });
  });

  it("reads a 502 as the VM up and the app down, not as an answer", async () => {
    mockFetch(502, undefined);

    await expect(apiRequest("/api/words")).rejects.toMatchObject({
      kind: "app-down",
      message: "The server is on, but echo-words isn't running on it.",
    });
    expect(serverReach.value).toMatchObject({ answeredAt: null, failure: { kind: "app-down" } });
  });

  it("counts any reply of the app, an error too, as the server answering", async () => {
    serverReach.value = { answeredAt: null, failure: { kind: "no-answer", at: 1 } };
    mockFetch(400, { detail: "Enter a word." });

    await expect(apiRequest("/api/words")).rejects.toMatchObject({ status: 400 });

    expect(serverReach.value.failure).toBeNull();
    expect(serverReach.value.answeredAt).toBeGreaterThan(0);
    expect(JSON.parse(localStorage.getItem("echo-words-server-reach"))).toEqual(serverReach.value);
  });

  it("passes a malformed answer through rather than calling it unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        headers: { get: () => null },
        json: async () => {
          throw new SyntaxError("Unexpected token");
        },
      })),
    );

    await expect(apiRequest("/api/status")).rejects.toBeInstanceOf(SyntaxError);
    expect(serverReach.value.failure).toBeNull();
  });
});
