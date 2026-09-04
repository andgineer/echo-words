import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

import { apiRequest } from "../src/api/_request.js";
import { entries } from "../src/composables/useEntries.js";
import { languages, selected } from "../src/composables/useLanguage.js";
import { locale } from "../src/i18n/index.js";
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
  locale.value = "en";
  localStorage.clear();
  apiRequest.mockReset();
  apiRequest.mockImplementation(async (path) => {
    if (path === "/api/languages") return OPTIONS;
    throw new Error(`Unexpected request: ${path}`);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  locale.value = "en";
  localStorage.clear();
});

// The receipt says what the submission became: the `?` shortcut stripped and the
// wording normalized, so the page never has to work that out for itself.
function accepts(entryId, { word = null, lookupOnly = false } = {}) {
  apiRequest.mockImplementation(async (path, init) => {
    if (path === "/api/languages") return OPTIONS;
    if (path === "/api/words") {
      return { entry_id: entryId, word: word ?? init.body.word, lookup_only: lookupOnly };
    }
    throw new Error(`Unexpected request: ${path}`);
  });
}

function unit(entryId, word, lang = "en", extra = {}) {
  return {
    entry_id: entryId,
    word,
    lang,
    language: lang === "de" ? "Deutsch" : "English",
    lookup_only: false,
    status: "done",
    shape: "unit",
    text: `${word} — meaning`,
    card_status: "added",
    card_kinds: ["Recognition"],
    ...extra,
  };
}

function textEntry() {
  return {
    entry_id: "entry-1",
    word: "Er steht jeden Morgen um sechs auf.",
    lang: "de",
    language: "Deutsch",
    lookup_only: false,
    shape: "text",
    status: "done",
    text: "Он встаёт каждое утро в шесть.",
    detail_available: false,
    segment_kind: "text",
    segments: [
      {
        label: "steht auf",
        reason: "Trennbares Verb.",
        context: "Er steht jeden Morgen um sechs auf.",
      },
    ],
  };
}

describe("AddView", () => {
  it("renders the language row, one field, and the empty state", async () => {
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.findAll(".lang-btn").map((button) => button.text())).toEqual([
      "English",
      "Deutsch",
    ]);
    expect(wrapper.get('[data-testid="lang-en"]').classes()).toContain("active");
    expect(wrapper.get("#word").attributes("placeholder")).toBe("a word or a phrase");
    expect(wrapper.text()).toContain("Word analyses will appear here");
    // The field label, the lookup checkbox and undo are all gone; the placeholder
    // carries the whole instruction and the card carries the deletion.
    expect(wrapper.find("label[for='word']").exists()).toBe(false);
    expect(wrapper.find(".lookup").exists()).toBe(false);
    expect(wrapper.find(".undo").exists()).toBe(false);
    expect(wrapper.find(".chips").exists()).toBe(false);
  });

  it("submits the word for the selected language and shows it pending at once", async () => {
    accepts("entry-1");
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.get('[data-testid="lang-de"]').trigger("click");
    await wrapper.get("#word").setValue("Straße");

    await wrapper.get(".submit").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/words", {
      method: "POST",
      body: {
        word: "Straße",
        lang: "de",
        lookup_only: false,
        request_id: expect.any(String),
      },
    });
    // No event has arrived yet: the pending state is the app's own answer to the tap.
    expect(wrapper.get(".entry-title").text()).toBe("Straße");
    expect(wrapper.get(".working").text()).toContain("Analysing “Straße”");
    expect(wrapper.get('[data-testid="chip-entry-1"]').classes()).toContain("running");
    expect(wrapper.get("#word").element.value).toBe("");
  });

  it("shows a backend validation hint without creating an entry", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      throw new Error("“English” needs the Latin script.");
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.get("#word").setValue("слово");

    await wrapper.get(".submit").trigger("click");
    await flushPromises();

    expect(wrapper.get(".hint").text()).toBe("“English” needs the Latin script.");
    expect(wrapper.find(".deck").exists()).toBe(false);
  });

  it("queues a word when its POST cannot reach the backend", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      throw new TypeError("Failed to fetch");
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.get("#word").setValue("offline");

    await wrapper.get(".submit").trigger("click");
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
    expect(wrapper.get(".hint").text()).toContain("will be sent later");
    expect(wrapper.get("#word").element.value).toBe("");
  });

  it("passes punctuation on a direct single-word submission to server validation", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") throw new Error("Letters, spaces, hyphens and apostrophes only.");
      throw new Error(`Unexpected request: ${path}`);
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.get("#word").setValue("hello!");

    await wrapper.get(".submit").trigger("click");
    await flushPromises();

    expect(apiRequest.mock.calls.find(([path]) => path === "/api/words")[1].body.word).toBe(
      "hello!",
    );
    expect(wrapper.get(".hint").text()).toBe("Letters, spaces, hyphens and apostrophes only.");
  });

  it("posts a multi-word input whole and never asks which word was meant", async () => {
    accepts("entry-1");
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.get('[data-testid="lang-de"]').trigger("click");
    await wrapper.get("#word").setValue("Rad fahren");

    await wrapper.get(".submit").trigger("click");
    await flushPromises();

    expect(apiRequest.mock.calls.find(([path]) => path === "/api/words")[1].body).toEqual({
      word: "Rad fahren",
      lang: "de",
      lookup_only: false,
      request_id: expect.any(String),
    });
  });

  // The checkbox is gone; the shortcut it duplicated is not.
  it("leaves a leading lookup shortcut to the backend", async () => {
    accepts("entry-1");
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.get("#word").setValue("? kick the bucket");

    await wrapper.get(".submit").trigger("click");
    await flushPromises();

    const body = apiRequest.mock.calls.find(([path]) => path === "/api/words")[1].body;
    expect(body.word).toBe("? kick the bucket");
    expect(body.lookup_only).toBe(false);
  });

  // Nothing after the receipt carries the word, so a guess here would stay in the rail.
  it("puts the submission in the rail as the backend read it, not as it was typed", async () => {
    accepts("entry-1", { word: "kick the bucket", lookupOnly: true });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.get("#word").setValue("? kick the bucket");

    await wrapper.get(".submit").trigger("click");
    await flushPromises();

    expect(wrapper.get('[data-testid="chip-entry-1"]').text()).toBe("kick the bucket");
    expect(wrapper.get(".entry-title").text()).toBe("kick the bucket");
    expect(entries.value[0].lookup_only).toBe(true);
  });

  describe("the rail", () => {
    it("shows only the selected language's entries, newest first", async () => {
      entries.value = [
        unit("entry-3", "Straße", "de"),
        unit("entry-2", "window", "en"),
        unit("entry-1", "house", "en"),
      ];
      const wrapper = mount(AddView);
      await flushPromises();

      expect(wrapper.findAll(".chip").map((chip) => chip.text())).toEqual(["window", "house"]);
      expect(wrapper.get(".entry-title").text()).toBe("window");

      await wrapper.get('[data-testid="lang-de"]').trigger("click");
      await flushPromises();

      expect(wrapper.findAll(".chip").map((chip) => chip.text())).toEqual(["Straße"]);
      expect(wrapper.get(".entry-title").text()).toBe("Straße");
    });

    it("opens the entry whose chip was tapped", async () => {
      entries.value = [unit("entry-2", "window"), unit("entry-1", "house")];
      const wrapper = mount(AddView);
      await flushPromises();
      expect(wrapper.get(".entry-title").text()).toBe("window");

      await wrapper.get('[data-testid="chip-entry-1"]').trigger("click");
      await flushPromises();

      expect(wrapper.get(".entry-title").text()).toBe("house");
      expect(wrapper.get('[data-testid="chip-entry-1"]').classes()).toContain("active");
    });

    it("walks the rail when the card is swiped, and stops at either end", async () => {
      entries.value = [unit("entry-2", "window"), unit("entry-1", "house")];
      const wrapper = mount(AddView);
      await flushPromises();

      const deck = wrapper.get(".deck");
      await deck.trigger("pointerdown", { clientX: 200 });
      await deck.trigger("pointermove", { clientX: 100 });
      await deck.trigger("pointerup");
      await flushPromises();
      expect(wrapper.get(".entry-title").text()).toBe("house");

      // Nothing older to move on to; the card stays where it is.
      await deck.trigger("pointerdown", { clientX: 200 });
      await deck.trigger("pointermove", { clientX: 100 });
      await deck.trigger("pointerup");
      await flushPromises();
      expect(wrapper.get(".entry-title").text()).toBe("house");

      await deck.trigger("pointerdown", { clientX: 100 });
      await deck.trigger("pointermove", { clientX: 200 });
      await deck.trigger("pointerup");
      await flushPromises();
      expect(wrapper.get(".entry-title").text()).toBe("window");
    });

    it("returns each language to the word it was left on", async () => {
      entries.value = [
        unit("entry-4", "Fenster", "de"),
        unit("entry-3", "Straße", "de"),
        unit("entry-2", "window", "en"),
        unit("entry-1", "house", "en"),
      ];
      const wrapper = mount(AddView);
      await flushPromises();

      await wrapper.get('[data-testid="chip-entry-1"]').trigger("click");
      await wrapper.get('[data-testid="lang-de"]').trigger("click");
      await flushPromises();
      expect(wrapper.get(".entry-title").text()).toBe("Fenster");

      await wrapper.get('[data-testid="lang-en"]').trigger("click");
      await flushPromises();

      expect(wrapper.get(".entry-title").text()).toBe("house");
    });

    it("has no rail and no card for a language with nothing in it yet", async () => {
      entries.value = [unit("entry-1", "house", "en")];
      const wrapper = mount(AddView);
      await flushPromises();

      await wrapper.get('[data-testid="lang-de"]').trigger("click");
      await flushPromises();

      expect(wrapper.find(".chips").exists()).toBe(false);
      expect(wrapper.find(".deck").exists()).toBe(false);
      expect(wrapper.get(".empty").text()).toBe("Word analyses will appear here.");
    });

    // A number and a pair of arrows say less than the chip under the card does.
    it("shows no pager", async () => {
      entries.value = [unit("entry-2", "window"), unit("entry-1", "house")];
      const wrapper = mount(AddView);
      await flushPromises();

      expect(wrapper.text()).not.toContain("1 / 2");
      expect(wrapper.find(".pager").exists()).toBe(false);
    });
  });

  describe("the controls on the open card", () => {
    it("asks the backend to switch onto the suggested spelling", async () => {
      entries.value = [unit("entry-1", "envi", "en", { suggestion: "envy" })];
      apiRequest.mockImplementation(async (path) => {
        if (path === "/api/languages") return OPTIONS;
        if (path === "/api/words/entry-1/switch") return { queued: true };
        throw new Error(`Unexpected request: ${path}`);
      });
      const wrapper = mount(AddView);
      await flushPromises();

      await wrapper.get(".correction").trigger("click");
      await flushPromises();

      expect(apiRequest).toHaveBeenCalledWith("/api/words/entry-1/switch", { method: "POST" });
    });

    it("deletes only the open card's own note, and only once confirmed", async () => {
      await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card deletion");
      entries.value = [unit("entry-2", "window"), unit("entry-1", "house")];
      apiRequest.mockImplementation(async (path) => {
        if (path === "/api/languages") return OPTIONS;
        if (path === "/api/words/entry-2/delete-card") return { deleted: "window" };
        throw new Error(`Unexpected request: ${path}`);
      });
      const wrapper = mount(AddView);
      await flushPromises();

      await wrapper.get(".delete-card").trigger("click");
      await flushPromises();
      expect(
        apiRequest.mock.calls.filter(([path]) => path.endsWith("/delete-card")),
      ).toHaveLength(0);

      await wrapper.get(".confirm-yes").trigger("click");
      await flushPromises();

      expect(
        apiRequest.mock.calls.filter(([path]) => path.endsWith("/delete-card")),
      ).toEqual([["/api/words/entry-2/delete-card", { method: "POST" }]]);
    });

    it("says on the card itself that its note had already gone", async () => {
      await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card deletion");
      entries.value = [unit("entry-2", "window"), unit("entry-1", "house")];
      apiRequest.mockImplementation(async (path) => {
        if (path === "/api/languages") return OPTIONS;
        if (path === "/api/words/entry-2/delete-card") throw new Error("nothing to delete");
        throw new Error(`Unexpected request: ${path}`);
      });
      const wrapper = mount(AddView);
      await flushPromises();

      await wrapper.get(".delete-card").trigger("click");
      await wrapper.get(".confirm-yes").trigger("click");
      await flushPromises();

      expect(wrapper.get(".entry-error").text()).toBe("nothing to delete");
      expect(wrapper.find(".hint").exists()).toBe(false);
    });

    it("marks the paid call as running on the card and on its chip", async () => {
      let settle;
      apiRequest.mockImplementation(async (path) => {
        if (path === "/api/languages") return OPTIONS;
        if (path === "/api/words/entry-1/detail") {
          return new Promise((resolve) => {
            settle = () => resolve({ queued: true });
          });
        }
        throw new Error(`Unexpected request: ${path}`);
      });
      entries.value = [unit("entry-1", "house", "en", { detail_available: true })];
      const wrapper = mount(AddView);
      await flushPromises();

      await wrapper.get(".detail").trigger("click");
      await flushPromises();

      expect(wrapper.find(".progress").exists()).toBe(true);
      expect(wrapper.get(".working").text()).toContain("Building the full entry");
      expect(wrapper.get('[data-testid="chip-entry-1"]').classes()).toContain("running");

      settle();
      await flushPromises();
      // Still running: only the streamed answer ends it.
      expect(wrapper.get('[data-testid="chip-entry-1"]').classes()).toContain("running");
    });

    it("stops saying a paid call is running when it is refused, on the card that asked", async () => {
      apiRequest.mockImplementation(async (path) => {
        if (path === "/api/languages") return OPTIONS;
        if (path === "/api/words/entry-1/detail") throw new Error("the daily cap is spent");
        throw new Error(`Unexpected request: ${path}`);
      });
      entries.value = [unit("entry-1", "house", "en", { detail_available: true })];
      const wrapper = mount(AddView);
      await flushPromises();

      await wrapper.get(".detail").trigger("click");
      await flushPromises();

      // The control lives on the card, so its refusal is read there and not over the rail.
      expect(wrapper.get(".entry-error").text()).toBe("the daily cap is spent");
      expect(wrapper.find(".hint").exists()).toBe(false);
      expect(wrapper.find(".progress").exists()).toBe(false);
      expect(wrapper.get('[data-testid="chip-entry-1"]').classes()).not.toContain("running");
    });

    it("shows an article the backend already had without waiting on an event", async () => {
      apiRequest.mockImplementation(async (path) => {
        if (path === "/api/languages") return OPTIONS;
        if (path === "/api/words/entry-1/detail") {
          return { entry_id: "entry-1", detail_html: "<p>kept</p>", cached: true };
        }
        throw new Error(`Unexpected request: ${path}`);
      });
      entries.value = [unit("entry-1", "house", "en", { detail_available: true })];
      const wrapper = mount(AddView);
      await flushPromises();

      await wrapper.get(".detail").trigger("click");
      await flushPromises();

      expect(wrapper.get(".entry-detail").html()).toContain("kept");
      expect(wrapper.find(".progress").exists()).toBe(false);
    });

    it("offers a failed entry back as a chip instead of asking for it to be retyped", async () => {
      entries.value = [
        {
          entry_id: "entry-1",
          word: "Ampel",
          lang: "de",
          language: "Deutsch",
          lookup_only: false,
          context: "Die Ampel ist rot.",
          requested_shape: "unit",
          status: "error",
          error: "analysis_failed",
        },
      ];
      accepts("entry-2");
      const wrapper = mount(AddView);
      await flushPromises();
      await wrapper.get('[data-testid="lang-de"]').trigger("click");
      await flushPromises();

      await wrapper.get(".entry-error .retry").trigger("click");
      await flushPromises();

      expect(apiRequest).toHaveBeenCalledWith("/api/words", {
        method: "POST",
        body: {
          word: "Ampel",
          lang: "de",
          lookup_only: false,
          context: "Die Ampel ist rot.",
          shape: "unit",
          request_id: expect.any(String),
        },
      });
    });

    it("posts a tapped chip in the language of its own text, and opens the new entry",
      async () => {
        await labelBehavior(
          EPIC.VOCABULARY_ANALYSIS,
          FEATURE.INPUT_AND_LANGUAGES,
          "Word submission",
        );
        accepts("entry-2");
        entries.value = [textEntry()];
        const wrapper = mount(AddView);
        await flushPromises();
        await wrapper.get('[data-testid="lang-de"]').trigger("click");
        await flushPromises();

        await wrapper.get(".segment-label").trigger("click");
        await flushPromises();

        expect(apiRequest).toHaveBeenCalledWith("/api/words", {
          method: "POST",
          body: {
            word: "steht auf",
            lang: "de",
            lookup_only: false,
            context: "Er steht jeden Morgen um sechs auf.",
            shape: "unit",
            request_id: expect.any(String),
          },
        });
        expect(entries.value.find((entry) => entry.entry_id === "entry-2").language).toBe(
          "Deutsch",
        );
        // The tapped word is what the reader wants to read, so it is what opens.
        expect(wrapper.get(".entry-title").text()).toBe("steht auf");
        expect(wrapper.get('[data-testid="chip-entry-2"]').classes()).toContain("active");
      });
  });

  it("documents the lookup shortcut and what becomes of a misspelling", async () => {
    const wrapper = mount(AddView);
    await flushPromises();

    await wrapper.get(".about-toggle").trigger("click");

    const help = wrapper.get(".about-text").text();
    expect(help).toContain("“? word”");
    expect(help).toContain("said above the analysis");
    expect(help).toContain("will not invent a word");
    // The checkbox it used to open with no longer exists.
    expect(help).not.toContain("checkbox");
  });
});
