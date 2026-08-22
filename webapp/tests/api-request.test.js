import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../src/api/_request.js";
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
  locale.value = "en";
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
      status: 502,
      headers: { get: () => null },
      json: async () => {
        throw new Error("not JSON");
      },
    }));
    vi.stubGlobal("fetch", fetch);

    await expect(apiRequest("/api/words")).rejects.toMatchObject({
      message: "HTTP 502",
      status: 502,
    });
  });
});
