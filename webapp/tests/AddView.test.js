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

function textEntry(segments = [
  { label: "aufstehen", surface: "steht … auf", reason: "Trennbares Verb." },
  { label: "ausfallen", surface: "fällt … aus", reason: "Trennbares Verb." },
]) {
  return {
    entry_id: "entry-1",
    word: "Er steht jeden Morgen um sechs auf.",
    lang: "de",
    language: "Deutsch",
    lookup_only: true,
    shape: "text",
    status: "done",
    text: "Он встаёт каждое утро в шесть.",
    card_status: "text",
    detail_available: false,
    segments,
  };
}

describe("AddView", () => {
  it("renders the configured language selector and M1 controls", async () => {
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.findAll("#lang option").map((option) => option.text())).toEqual([
      "English",
      "Deutsch",
    ]);
    expect(wrapper.find("#word").exists()).toBe(true);
    expect(wrapper.find('.lookup input[type="checkbox"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("Look up only");
    expect(wrapper.text()).toContain("Word analyses will appear here");
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
    expect(wrapper.find(".entry-meta").text()).toContain("Deutsch · no card");
    expect(wrapper.find("#word").element.value).toBe("");
    expect(wrapper.find('.lookup input[type="checkbox"]').element.checked).toBe(false);
  });

  it("shows a backend validation hint without creating an entry", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      throw new Error("“English” needs the Latin script.");
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find("#word").setValue("слово");

    await wrapper.find(".btn-primary").trigger("click");
    await flushPromises();

    expect(wrapper.find(".hint").text()).toBe("“English” needs the Latin script.");
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
    expect(wrapper.find(".hint").text()).toContain("will be sent later");
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
      card_status: "added",
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-card-status").text()).toBe("✅ added to Anki");
  });

  it("names the cards a note produced, counting the pair a context makes", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    entries.value = [{
      entry_id: "entry-1",
      word: "bank",
      language: "English",
      status: "done",
      text: "meaning",
      card_status: "added",
      card_kinds: ["Recognition", "Recall", "ContextRecognition", "ContextProduction"],
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-card-status").text()).toBe(
      "✅ 4 cards: recognition, recall, context ×2",
    );

    locale.value = "ru";
    await flushPromises();

    expect(wrapper.find(".entry-card-status").text()).toBe(
      "✅ 4 карточки: узнавание, воспроизведение, контекст ×2",
    );
  });

  it("counts a split into one card per sense, and one card in the singular", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    entries.value = [
      {
        entry_id: "entry-1",
        word: "bank",
        language: "English",
        status: "done",
        text: "meaning",
        card_status: "added",
        card_kinds: ["Recognition", "SenseRecall1", "SenseRecall2"],
      },
      {
        entry_id: "entry-2",
        word: "Wort",
        language: "German",
        status: "done",
        text: "meaning",
        card_status: "added",
        card_kinds: ["Recognition"],
      },
    ];
    locale.value = "ru";
    const wrapper = mount(AddView);
    await flushPromises();

    const lines = wrapper.findAll(".entry-card-status").map((node) => node.text());
    expect(lines[0]).toBe("✅ 3 карточки: узнавание, по значению ×2");
    expect(lines[1]).toBe("✅ 1 карточка: узнавание");
  });

  it("counts five cards in the form Russian actually uses", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    entries.value = [{
      entry_id: "entry-1",
      word: "bank",
      language: "English",
      status: "done",
      text: "meaning",
      card_status: "added",
      card_kinds: [
        "Recognition",
        "ContextRecognition",
        "SenseRecall1",
        "SenseRecall2",
        "SenseRecall3",
      ],
    }];
    locale.value = "ru";
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-card-status").text()).toBe(
      "✅ 5 карточек: узнавание, контекст, по значению ×3",
    );
  });

  it("falls back to the plain result when the kinds are not known", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    entries.value = [{
      entry_id: "entry-1",
      word: "bank",
      language: "English",
      status: "done",
      text: "meaning",
      card_status: "added",
      card_kinds: [],
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-card-status").text()).toBe("✅ added to Anki");
  });

  it("renders the Anki result in the interface language, switching with it", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    entries.value = [{
      entry_id: "entry-1",
      word: "Word",
      language: "English",
      status: "done",
      text: "meaning",
      card_status: "added",
      no_audio: true,
    }];
    const wrapper = mount(AddView);
    await flushPromises();
    expect(wrapper.find(".entry-card-status").text()).toBe("✅ added to Anki · 🔇 no audio");

    locale.value = "ru";
    await flushPromises();

    expect(wrapper.find(".entry-card-status").text()).toBe(
      "✅ добавлено в Anki · 🔇 без озвучки",
    );
  });

  it("shows an Anki failure reason verbatim, and a failed analysis in the interface language",
    async () => {
      await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
      entries.value = [
        {
          entry_id: "entry-1",
          word: "Word",
          language: "English",
          status: "done",
          text: "meaning",
          card_status: "failed",
          card_error: "note type EchoWords is misconfigured",
        },
        {
          entry_id: "entry-2",
          word: "Other",
          language: "English",
          status: "error",
          error: "analysis_failed",
        },
      ];
      locale.value = "ru";
      const wrapper = mount(AddView);
      await flushPromises();

      expect(wrapper.find(".entry-card-status").text()).toBe(
        "⚠️ note type EchoWords is misconfigured",
      );
      expect(wrapper.find(".entry-error").text()).toBe(
        "Не удалось получить разбор. Попробуйте отправить слово ещё раз.",
      );
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

  it("plays the whole text beside the pronunciation of the unit taken from it", async () => {
    await labelBehavior(EPIC.PRONUNCIATION, FEATURE.AUDIO_DELIVERY, "Playback");
    entries.value = [{
      entry_id: "entry-1",
      word: "aufstehen",
      language: "Deutsch",
      lookup_only: false,
      status: "done",
      text: "<b>aufstehen</b> — вставать",
      context: "Er steht jeden Morgen um sechs auf.",
      audio_url: "/api/audio/pronunciation-aabbccddeeff00112233.mp3",
      context_audio_url: "/api/audio/pronunciation-1122334455667788990a.mp3",
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    const players = wrapper.findAll("audio.entry-audio");
    expect(players.map((player) => player.attributes("src"))).toEqual([
      entries.value[0].audio_url,
      entries.value[0].context_audio_url,
    ]);
    // Two players may not talk over each other: only the unit's own audio starts by itself.
    expect(players[1].attributes()).not.toHaveProperty("autoplay");
    expect(wrapper.find(".context-audio-title").text()).toBe("The whole text");
  });

  it("leaves a text answer with the single player that voices it whole", async () => {
    await labelBehavior(EPIC.PRONUNCIATION, FEATURE.AUDIO_DELIVERY, "Playback");
    entries.value = [{
      ...textEntry(),
      audio_url: "/api/audio/pronunciation-1122334455667788990a.mp3",
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    const players = wrapper.findAll("audio.entry-audio");
    expect(players).toHaveLength(1);
    expect(players[0].attributes("src")).toBe(entries.value[0].audio_url);
    expect(players[0].attributes()).toHaveProperty("autoplay");
    expect(wrapper.find(".context-audio-title").exists()).toBe(false);
  });

  it("documents both lookup shortcuts and the reversible correction control", async () => {
    const wrapper = mount(AddView);
    await flushPromises();

    await wrapper.find(".about-toggle").trigger("click");

    expect(wrapper.find(".about-text").text()).toContain("“? word”");
    expect(wrapper.find(".about-text").text()).toContain("✏️ Correct");
    expect(wrapper.find(".about-text").text()).toContain("brings the original back");
  });

  it("passes punctuation on a direct single-word submission to server validation", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") throw new Error("Letters, spaces, hyphens and apostrophes only.");
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
    expect(wrapper.find(".hint").text()).toBe("Letters, spaces, hyphens and apostrophes only.");
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

    expect(wrapper.find(".correction").text()).toContain("✏️ Correct to “receive”");
    expect(wrapper.find(".rebuild").exists()).toBe(true);
    expect(wrapper.find(".detail").element.disabled).toBe(false);
    expect(wrapper.find(".entry-meta").text()).toContain("English · free-flash");
  });

  it("posts a multi-word input whole and never asks which word was meant", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") return { entry_id: "entry-1" };
      throw new Error(`Unexpected request: ${path}`);
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find("#lang").setValue("de");
    await wrapper.find("#word").setValue("Rad fahren");

    await wrapper.find(".btn-primary").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/words", {
      method: "POST",
      body: {
        word: "Rad fahren",
        lang: "de",
        lookup_only: false,
        request_id: expect.any(String),
      },
    });
    expect(wrapper.find(".picker").exists()).toBe(false);
  });

  it("leaves a leading lookup shortcut to the backend", async () => {
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") return { entry_id: "entry-1" };
      throw new Error(`Unexpected request: ${path}`);
    });
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find("#word").setValue("? kick the bucket");

    await wrapper.find(".btn-primary").trigger("click");
    await flushPromises();

    expect(apiRequest.mock.calls.find(([path]) => path === "/api/words")[1].body.word).toBe(
      "? kick the bucket",
    );
  });

  it("offers the suggested units of a running text as buttons", async () => {
    await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.ANSWER_DELIVERY, "Suggested units");
    entries.value = [textEntry()];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.findAll(".segment-label").map((button) => button.text())).toEqual([
      "aufstehen",
      "ausfallen",
    ]);
    expect(wrapper.find(".segments").text()).toContain("Worth looking up on their own");
    expect(wrapper.find(".segment-surface").text()).toBe("steht … auf");
    expect(wrapper.find(".segment-reason").text()).toBe("Trennbares Verb.");
    expect(wrapper.find(".entry-meta").text()).toContain("Deutsch · text — no card");
  });

  it("posts a tapped unit in the language of its own text, carrying that text as context", async () => {
    await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.INPUT_AND_LANGUAGES, "Word submission");
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") return { entry_id: "entry-2" };
      throw new Error(`Unexpected request: ${path}`);
    });
    entries.value = [textEntry()];
    const wrapper = mount(AddView);
    await flushPromises();
    expect(wrapper.find("#lang").element.value).toBe("en");

    await wrapper.find(".segment-label").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/words", {
      method: "POST",
      body: {
        word: "aufstehen",
        lang: "de",
        lookup_only: false,
        context: "Er steht jeden Morgen um sechs auf.",
        shape: "unit",
        request_id: expect.any(String),
      },
    });
    expect(entries.value.find((entry) => entry.entry_id === "entry-2").language).toBe("Deutsch");
  });

  it("keeps the lookup-only choice when a suggested unit is tapped", async () => {
    await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.INPUT_AND_LANGUAGES, "Word submission");
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") return { entry_id: "entry-2" };
      throw new Error(`Unexpected request: ${path}`);
    });
    entries.value = [textEntry()];
    const wrapper = mount(AddView);
    await flushPromises();
    await wrapper.find('.lookup input[type="checkbox"]').setValue(true);

    await wrapper.find(".segment-label").trigger("click");
    await flushPromises();

    expect(
      apiRequest.mock.calls.find(([path]) => path === "/api/words")[1].body.lookup_only,
    ).toBe(true);
  });

  it("renders a suggested unit as text, so model markup can never become markup", async () => {
    await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.ANSWER_DELIVERY, "Suggested units");
    entries.value = [
      textEntry([
        {
          label: "<img src=x onerror=alert(1)>",
          surface: "<b>steht</b>",
          reason: "<script>alert(2)</script>",
        },
      ]),
    ];
    const wrapper = mount(AddView);
    await flushPromises();

    const segment = wrapper.find(".segment");
    expect(segment.find(".segment-label").text()).toBe("<img src=x onerror=alert(1)>");
    expect(segment.html()).toContain("&lt;img src=x onerror=alert(1)&gt;");
    expect(segment.find("img").exists()).toBe(false);
    expect(segment.find("b").exists()).toBe(false);
    expect(segment.find("script").exists()).toBe(false);
  });

  it("offers neither rebuild nor deeper analysis on a running-text entry", async () => {
    await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.ANSWER_DELIVERY, "Suggested units");
    entries.value = [textEntry()];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".rebuild").exists()).toBe(false);
    expect(wrapper.find(".detail").exists()).toBe(false);
  });
});
