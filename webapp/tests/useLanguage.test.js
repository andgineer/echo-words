import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

const OPTIONS = [
  { code: "en", name: "English" },
  { code: "de", name: "Deutsch" },
];

beforeEach(async () => {
  await labelBehavior(
    EPIC.VOCABULARY_ANALYSIS,
    FEATURE.INPUT_AND_LANGUAGES,
    "Language selection",
  );
  localStorage.clear();
  vi.resetModules();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

async function loadSubject() {
  const api = await import("../src/api/_request.js");
  const subject = await import("../src/composables/useLanguage.js");
  return { ...api, ...subject };
}

describe("useLanguage", () => {
  it("starts with the selection remembered by the browser", async () => {
    localStorage.setItem("echo-words.lang", "de");

    const { selected } = await loadSubject();

    expect(selected.value).toBe("de");
  });

  it("loads the configured languages and keeps a known selection", async () => {
    localStorage.setItem("echo-words.lang", "de");
    const { apiRequest, languages, selected, loadLanguages } = await loadSubject();
    apiRequest.mockResolvedValue(OPTIONS);

    await loadLanguages();

    expect(apiRequest).toHaveBeenCalledWith("/api/languages");
    expect(languages.value).toEqual(OPTIONS);
    expect(selected.value).toBe("de");
  });

  it("replaces a stale selection with the first configured language and persists it", async () => {
    localStorage.setItem("echo-words.lang", "fr");
    const { apiRequest, selected, loadLanguages } = await loadSubject();
    apiRequest.mockResolvedValue(OPTIONS);

    await loadLanguages();
    await nextTick();

    expect(selected.value).toBe("en");
    expect(localStorage.getItem("echo-words.lang")).toBe("en");
  });

  it("uses an empty selection when the backend has no configured languages", async () => {
    const { apiRequest, selected, loadLanguages } = await loadSubject();
    apiRequest.mockResolvedValue([]);

    await loadLanguages();

    expect(selected.value).toBe("");
  });

  it("does not fail the app when browser storage is unavailable", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });

    const { selected } = await loadSubject();

    expect(selected.value).toBe("");
  });
});
