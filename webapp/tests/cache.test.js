import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  cachedRequest, DAY_MS, initializeCache, invalidateCache, readCache, writeCache,
} from "../src/api/cache.js";
import { apiRequest } from "../src/api/_request.js";

vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

beforeEach(() => {
  localStorage.clear();
  apiRequest.mockReset();
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-08T00:00:00Z"));
});

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("uses a persisted snapshot for 24 hours, then refreshes once", async () => {
  writeCache("/catalog", ["old"]);
  vi.advanceTimersByTime(DAY_MS - 1);
  expect(await cachedRequest("/catalog")).toEqual(["old"]);
  expect(apiRequest).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1);
  apiRequest.mockResolvedValue(["new"]);
  expect(await cachedRequest("/catalog")).toEqual(["new"]);
  expect(await cachedRequest("/catalog")).toEqual(["new"]);
  expect(apiRequest).toHaveBeenCalledTimes(1);
});

it("shares an in-flight refresh between readers", async () => {
  apiRequest.mockResolvedValue(["new"]);
  await Promise.all([cachedRequest("/catalog"), cachedRequest("/catalog")]);
  expect(apiRequest).toHaveBeenCalledTimes(1);
});

it("returns stale editor data immediately while refreshing it in the background", async () => {
  writeCache("/catalog", ["old"], 1);
  let finish;
  apiRequest.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  expect(await cachedRequest("/catalog", { background: true })).toEqual(["old"]);
  const refreshed = cachedRequest("/catalog");
  finish(["new"]);
  expect(await refreshed).toEqual(["new"]);
  expect(readCache("/catalog").data).toEqual(["new"]);
});

it("retains stale data and attempts at most one refresh per day even offline", async () => {
  writeCache("/catalog", ["old"], 1);
  apiRequest.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ error: "bad" });
  expect(await cachedRequest("/catalog")).toEqual(["old"]);
  expect(await cachedRequest("/catalog")).toEqual(["old"]);
  expect(apiRequest).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(DAY_MS);
  expect(await cachedRequest("/catalog")).toEqual(["old"]);
  expect(apiRequest).toHaveBeenCalledTimes(2);
  expect(readCache("/catalog")).toMatchObject({ data: ["old"], fetchedAt: 1 });
});

it("refreshes a changed directory even within the TTL", async () => {
  writeCache("/catalog", ["old"]);
  invalidateCache("/catalog");
  apiRequest.mockResolvedValue(["edited"]);
  expect(await cachedRequest("/catalog")).toEqual(["edited"]);
});

it("recovers corrupt storage and reports a first-load network error", async () => {
  localStorage.setItem("echo-words.cache.v1:/catalog", "broken json");
  expect(readCache("/catalog")).toBeNull();
  apiRequest.mockRejectedValue(new Error("offline"));
  await expect(cachedRequest("/catalog")).rejects.toThrow("offline");
});

it("still serves fetched data when localStorage is blocked or full", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
  apiRequest.mockResolvedValue(["new"]);
  expect(await cachedRequest("/catalog")).toEqual(["new"]);
});

it("restores fallback data after a reload without fetching it", async () => {
  await writeCache("/catalog", ["saved"]);
  vi.resetModules();
  const restored = await import("../src/api/cache.js");
  await restored.initializeCache();
  expect(await restored.cachedRequest("/catalog")).toEqual(["saved"]);
  expect(apiRequest).not.toHaveBeenCalled();
});

it("does not hang startup on a blocked database or delete it", async () => {
  const request = {};
  vi.stubGlobal("indexedDB", { open: () => request });
  await writeCache("/catalog", ["fallback"]);
  const initializing = initializeCache();
  await vi.advanceTimersByTimeAsync(1500);
  await initializing;
  expect(readCache("/catalog").data).toEqual(["fallback"]);
  request.result = { close: vi.fn() };
  request.onsuccess();
  expect(request.result.close).toHaveBeenCalledTimes(1);
});
