import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { readFileSync } from "node:fs";

vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

import { apiRequest } from "../src/api/_request.js";
import { entries } from "../src/composables/useEntries.js";
import { languages, selected } from "../src/composables/useLanguage.js";
import AddView from "../src/views/AddView.vue";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

const OPTIONS = [
  { code: "en", name: "English" },
  { code: "de", name: "Deutsch" },
];

beforeEach(async () => {
  await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.INPUT_AND_LANGUAGES, "Word submission");
  languages.value = [];
  entries.value = [];
  selected.value = "";
  localStorage.clear();
  apiRequest.mockReset();
  apiRequest.mockImplementation(async (path) => {
    if (path === "/api/languages") return OPTIONS;
    throw new Error(`Unexpected request: ${path}`);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("AddView", () => {
  it("documents a Shortcut matcher that trims token-edge punctuation", () => {
    const readme = readFileSync("../README.md", "utf8");
    const documentedPattern = readme.match(/Use \*\*Match Text\*\* with\s+`([^`]+)`/u)?.[1];
    expect(documentedPattern).toBe(String.raw`\p{L}(?:[\p{L}\p{N}'’-]*[\p{L}\p{N}])?`);

    const shortcutMatcher = new RegExp(documentedPattern, "gu");
    const sharedText = "“don’t,” word' word’ go-over- '(Straße)'";
    expect([...sharedText.matchAll(shortcutMatcher)].map(([token]) => token)).toEqual([
      "don’t",
      "word",
      "word",
      "go-over",
      "Straße",
    ]);
  });

  it("renders the configured language selector and M1 controls", async () => {
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.findAll("#lang option").map((option) => option.text())).toEqual([
      "English",
      "Deutsch",
    ]);
    expect(wrapper.find("#word").exists()).toBe(true);
    expect(wrapper.find('.lookup input[type="checkbox"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("Только посмотреть");
    expect(wrapper.text()).toContain("Здесь появятся разборы слов");
  });

  it("submits the selected language and lookup-only flag, then renders the pending entry", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") {
        return { entry_id: "entry-1" };
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find("#lang").setValue("de");
    await wrapper.find("#word").setValue("Straße");
    await wrapper.find('.lookup input[type="checkbox"]').setValue(true);

    await wrapper.find(".btn-primary").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/words", {
      method: "POST",
      body: {
        word: "Straße",
        lang: "de",
        lookup_only: true,
        request_id: expect.any(String),
      },
    });
    expect(wrapper.find(".entry-head").text()).toContain("Straße");
    expect(wrapper.find(".entry-meta").text()).toContain("Deutsch · без карточки");
    expect(wrapper.find("#word").element.value).toBe("");
    expect(wrapper.find('.lookup input[type="checkbox"]').element.checked).toBe(false);
  });

  it("shows a backend validation hint without creating an entry", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      throw new Error("Для «English» нужна латиница.");
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find("#word").setValue("слово");

    await wrapper.find(".btn-primary").trigger("click");
    await flushPromises();

    expect(wrapper.find(".hint").text()).toBe("Для «English» нужна латиница.");
    expect(wrapper.find(".entry").exists()).toBe(false);
  });

  it("queues a word when its POST cannot reach the backend", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      throw new TypeError("Failed to fetch");
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find("#word").setValue("offline");

    await wrapper.find(".btn-primary").trigger("click");
    await flushPromises();

    const saved = JSON.parse(localStorage.getItem("echo-words-resend-queue"));
    expect(saved[0].body).toEqual({
      word: "offline",
      lang: "en",
      lookup_only: false,
      request_id: expect.any(String),
    });
    const posted = apiRequest.mock.calls.find(([path]) => path === "/api/words")[1].body;
    expect(saved[0].body.request_id).toBe(posted.request_id);
    expect(wrapper.find(".hint").text()).toContain("будет отправлено позже");
    expect(wrapper.find("#word").element.value).toBe("");
  });

  it("shows streamed text while an entry is still pending", async () => {
    entries.value = [{
      entry_id: "entry-1",
      word: "Word",
      language: "English",
      lookup_only: false,
      status: "pending",
      text: "<b>Word</b> — meaning",
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-text").html()).toContain("<b>Word</b> — meaning");
    expect(wrapper.find(".entry-head").exists()).toBe(false);
  });

  it("shows the Anki result attached to a completed answer", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    entries.value = [{
      entry_id: "entry-1",
      word: "Word",
      language: "English",
      lookup_only: false,
      status: "done",
      text: "<b>Word</b> — meaning",
      card_status: "✅ added to Anki",
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-card-status").text()).toBe("✅ added to Anki");
  });

  it("attaches a replayable pronunciation to a completed answer", async () => {
    await labelBehavior(EPIC.PRONUNCIATION, FEATURE.AUDIO_DELIVERY, "Playback");
    entries.value = [{
      entry_id: "entry-1",
      word: "Word",
      language: "English",
      lookup_only: false,
      status: "done",
      text: "<b>Word</b> — meaning",
      audio_url: "/api/audio/pronunciation-aabbccddeeff00112233.mp3",
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    const player = wrapper.find("audio.entry-audio");
    expect(player.attributes("src")).toBe(entries.value[0].audio_url);
    expect(player.attributes()).toHaveProperty("controls");
    expect(player.attributes()).toHaveProperty("autoplay");
  });

  it("documents both lookup shortcuts and the reversible correction control", async () => {
    const wrapper = mount(AddView);
    await flushPromises();

    await wrapper.find(".about-toggle").trigger("click");

    expect(wrapper.find(".about-text").text()).toContain("? слово");
    expect(wrapper.find(".about-text").text()).toContain("✏️ Исправить");
    expect(wrapper.find(".about-text").text()).toContain("вернуться обратно");
  });

  it("offers every word in a phrase and posts only after a choice", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") return { entry_id: "picked" };
      throw new Error(`Unexpected request: ${path}`);
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find("#word").setValue("He kicked the bucket.");

    await wrapper.find(".btn-primary").trigger("click");

    expect(wrapper.findAll(".picker-choice").map((button) => button.text())).toEqual([
      "He",
      "kicked",
      "the",
      "bucket",
    ]);
    expect(apiRequest).toHaveBeenCalledTimes(1);

    await wrapper.findAll(".picker-choice")[3].trigger("click");
    await flushPromises();
    expect(apiRequest).toHaveBeenCalledWith("/api/words", {
      method: "POST",
      body: {
        word: "bucket",
        lang: "en",
        lookup_only: false,
        context: "He kicked the bucket.",
        request_id: expect.any(String),
      },
    });
  });

  it("strips a leading lookup shortcut before building phrase choices", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") return { entry_id: "picked" };
      throw new Error(`Unexpected request: ${path}`);
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find("#word").setValue("? kick the bucket");
    await wrapper.find(".btn-primary").trigger("click");

    expect(wrapper.findAll(".picker-choice").map((button) => button.text())).toEqual([
      "kick",
      "the",
      "bucket",
    ]);
    expect(wrapper.text()).not.toContain("? kick");

    await wrapper.find(".picker-choice").trigger("click");
    await flushPromises();
    expect(apiRequest).toHaveBeenCalledWith("/api/words", {
      method: "POST",
      body: {
        word: "kick",
        lang: "en",
        lookup_only: true,
        context: "kick the bucket",
        request_id: expect.any(String),
      },
    });
  });

  it("passes punctuation on a direct single-word submission to server validation", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") throw new Error("Недопустимая пунктуация.");
      throw new Error(`Unexpected request: ${path}`);
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find("#word").setValue("hello!");

    await wrapper.find(".btn-primary").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/words", {
      method: "POST",
      body: {
        word: "hello!",
        lang: "en",
        lookup_only: false,
        request_id: expect.any(String),
      },
    });
    expect(wrapper.find(".hint").text()).toBe("Недопустимая пунктуация.");
  });

  it("clears phrase choices when input, language or lookup-only changes", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") return { entry_id: "picked" };
      throw new Error(`Unexpected request: ${path}`);
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find("#word").setValue("kick the bucket");
    await wrapper.find(".btn-primary").trigger("click");
    expect(wrapper.find(".picker").exists()).toBe(true);

    await wrapper.find("#word").setValue("changed phrase");
    expect(wrapper.find(".picker").exists()).toBe(false);

    await wrapper.find(".btn-primary").trigger("click");
    expect(wrapper.find(".picker").exists()).toBe(true);
    await wrapper.find("#lang").setValue("de");
    expect(wrapper.find(".picker").exists()).toBe(false);

    await wrapper.find("#lang").setValue("en");
    await wrapper.find(".btn-primary").trigger("click");
    expect(wrapper.find(".picker").exists()).toBe(true);
    await wrapper.find('.lookup input[type="checkbox"]').setValue(true);
    expect(wrapper.find(".picker").exists()).toBe(false);

    await wrapper.find(".btn-primary").trigger("click");
    await wrapper.find(".picker-choice").trigger("click");
    await flushPromises();
    expect(apiRequest).toHaveBeenLastCalledWith("/api/words", {
      method: "POST",
      body: {
        word: "changed",
        lang: "en",
        lookup_only: true,
        context: "changed phrase",
        request_id: expect.any(String),
      },
    });
  });

  it("renders correction, rebuild and detail controls on a finished history entry", async () => {
    entries.value = [{
      entry_id: "entry-1",
      word: "recieve",
      language: "English",
      lookup_only: false,
      status: "done",
      text: "analysis",
      suggestion: "receive",
      correction_reversed: false,
      detail_available: true,
      model: "free-flash",
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".correction").text()).toContain("✏️ Исправить на «receive»");
    expect(wrapper.find(".rebuild").exists()).toBe(true);
    expect(wrapper.find(".detail").element.disabled).toBe(false);
    expect(wrapper.find(".entry-meta").text()).toContain("English · free-flash");
  });

  it("disables phrase choices while their POST is pending", async () => {
    let resolveWord;
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") {
        return new Promise((resolve) => { resolveWord = resolve; });
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find("#word").setValue("kick the bucket");
    await wrapper.find(".btn-primary").trigger("click");

    const choice = wrapper.find(".picker-choice");
    await choice.trigger("click");
    expect(choice.element.disabled).toBe(true);
    await choice.trigger("click");
    expect(apiRequest.mock.calls.filter(([path]) => path === "/api/words")).toHaveLength(1);

    resolveWord({ entry_id: "picked" });
    await flushPromises();
  });
});
