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
  {
    label: "steht auf",
    reason: "Trennbares Verb.",
    context: "Er steht jeden Morgen um sechs auf.",
  },
  {
    label: "fällt aus",
    reason: "Trennbares Verb.",
    context: "Er steht jeden Morgen um sechs auf.",
  },
]) {
  return {
    entry_id: "entry-1",
    word: "Er steht jeden Morgen um sechs auf.",
    lang: "de",
    language: "Deutsch",
    lookup_only: false,
    shape: "text",
    status: "done",
    text: "Он встаёт каждое утро в шесть.",
    card_status: "text",
    detail_available: false,
    segment_kind: "text",
    segments,
  };
}

function senseEntry() {
  return {
    entry_id: "entry-1",
    word: "bank",
    lang: "en",
    language: "English",
    lookup_only: false,
    shape: "unit",
    status: "done",
    text: "берег",
    card_status: "added",
    card_kinds: ["Recognition", "Recall", "ContextRecognition", "ContextProduction"],
    context: "We sat on the bank.",
    segment_kind: "senses",
    segments: [
      { label: "bank", reason: "банк", context: "The bank opens at nine." },
      {
        label: "bank",
            reason: "склон",
        context: "The bank of the hill is steep.",
      },
    ],
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


  it("says which word the card is for when a misspelling was corrected onto it", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    entries.value = [{
      entry_id: "entry-1",
      word: "envi",
      language: "English",
      status: "done",
      shape: "unit",
      text: "<b>envy</b> — зависть",
      card_status: "added",
      card_kinds: ["Recognition"],
      analysed_as: "envy",
      typo_suspected: true,
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-notice").text()).toBe(
      "“envi” looks like a typo, so the card is for “envy” instead.",
    );
    const html = wrapper.html();
    expect(html.indexOf("entry-notice")).toBeLessThan(html.indexOf("entry-text"));
  });

  it("says nothing about the spelling when the card is for the word as typed", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    entries.value = [{
      entry_id: "entry-1",
      word: "receive",
      language: "English",
      status: "done",
      shape: "unit",
      text: "<b>receive</b> — получать",
      card_status: "added",
      card_kinds: ["Recognition"],
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-notice").exists()).toBe(false);
  });

  it("shows no card and no article for wording the answer would not vouch for", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    entries.value = [{
      entry_id: "entry-1",
      word: "blorptium",
      language: "English",
      status: "done",
      text: "",
      card_status: "unattested",
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-notice").text()).toBe(
      "“blorptium” — the model does not vouch for this word. No card was made.",
    );
    expect(wrapper.find(".entry-card-status").text()).toBe("🚫 no card");
    expect(wrapper.find(".entry-text").exists()).toBe(false);
    expect(wrapper.find(".rebuild").exists()).toBe(false);
  });

  it("does not tell a lookup that a card was withheld from it", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    entries.value = [{
      entry_id: "entry-1",
      word: "blorptium",
      language: "English",
      status: "done",
      text: "",
      card_status: "unattested",
      lookup_only: true,
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-notice").text()).toBe(
      "“blorptium” — the model does not vouch for this word.",
    );
  });

  it("points the offer back once the entry shows the other spelling", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.CORRECTION_AND_DETAIL, "Correction control");
    entries.value = [{
      entry_id: "entry-1",
      word: "envy",
      language: "English",
      status: "done",
      shape: "unit",
      text: "<b>envy</b> — зависть",
      card_status: "added",
      card_kinds: ["Recognition"],
      suggestion: "envi",
      showing_other_spelling: true,
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    // Calling the learner's own spelling "the usual one" is what the flag prevents.
    expect(wrapper.find(".entry-notice").text()).toContain(
      "This is “envy”, not the “envi” you typed.",
    );
    expect(wrapper.find(".correction").text()).toBe("↩︎ Go back to a card for “envi”");
  });

  // Reached after a switch back: the learner returned to their own spelling, this
  // answer accepted it as a word, and the other one stays on offer beside it.
  it("does not call a misspelling a more usual spelling on a lookup", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.CORRECTION_AND_DETAIL, "Correction control");
    entries.value = [{
      entry_id: "entry-1",
      word: "recieve",
      language: "English",
      status: "done",
      shape: "unit",
      text: "<b>recieve</b> — получать",
      card_status: "lookup_only",
      suggestion: "receive",
      typo_suspected: true,
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    // There is no card here, and the answer called this spelling wrong — the other
    // wording is the correction, not a more usual way of writing a good word.
    expect(wrapper.find(".entry-notice").text()).toContain(
      "“recieve” looks like a typo for “receive”",
    );
  });

  it("names the other spelling once the entry is back on the one typed", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.CORRECTION_AND_DETAIL, "Correction control");
    entries.value = [{
      entry_id: "entry-1",
      word: "envi",
      language: "English",
      status: "done",
      shape: "unit",
      text: "<b>envi</b> — зависть",
      card_status: "added",
      card_kinds: ["Recognition"],
      suggestion: "envy",
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-notice").text()).toContain(
      "The card is for “envi”; “envy” is named the more usual spelling.",
    );
    expect(wrapper.find(".correction").text()).toBe("Replace the card with “envy”");
  });

  it("names the word a card is for when it is not the word that was typed", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    entries.value = [{
      entry_id: "entry-1",
      word: "envi",
      language: "English",
      status: "done",
      shape: "unit",
      text: "<b>environment</b> — окружающая среда",
      card_status: "added",
      card_kinds: ["Recognition"],
      analysed_as: "environment",
      typo_suspected: false,
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    // Saying nothing here is how a learner ends up drilling a word they never typed;
    // calling it a typo is how every inflected submission gets accused of one.
    expect(wrapper.find(".entry-notice").text()).toBe(
      "The card is for “environment”, not the “envi” you typed.",
    );
  });

  it("makes no card for a spelling the answer itself called wrong", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    entries.value = [{
      entry_id: "entry-1",
      word: "recieve",
      language: "English",
      status: "done",
      shape: "unit",
      text: "<b>recieve</b> — получать",
      card_status: "misspelled",
      suggestion: "receive",
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-notice").text()).toContain(
      "“recieve” looks like a typo for “receive”, so no card was made.",
    );
    // There is no card to replace, so the offer says what it will actually do.
    expect(wrapper.find(".correction").text()).toBe("Analyse “receive” instead");
  });

  it("keeps the way back when the switch could not store its card", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.CORRECTION_AND_DETAIL, "Correction control");
    entries.value = [{
      entry_id: "entry-1",
      word: "receive",
      language: "English",
      status: "done",
      shape: "unit",
      text: "<b>receive</b> — получать",
      card_status: "failed",
      card_kept: true,
      suggestion: "recieve",
      showing_other_spelling: true,
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    // Without this the entry shows another word than the deck holds, says nothing
    // about it, and leaves retyping as the only way back.
    expect(wrapper.find(".entry-notice").text()).toContain(
      "This is “receive”, not the “recieve” you typed.",
    );
    expect(wrapper.find(".correction").text()).toBe("↩︎ Go back to a card for “recieve”");
    expect(wrapper.find(".entry-card-status").text()).toContain("the card you had is untouched");
  });

  it("says which word a corrected lookup analysed, though it carded nothing", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    entries.value = [{
      entry_id: "entry-1",
      word: "recieve",
      language: "English",
      status: "done",
      shape: "unit",
      text: "<b>receive</b> — получать",
      card_status: "lookup_only",
      analysed_as: "receive",
      typo_suspected: true,
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-notice").text()).toBe(
      "This is “receive”, not the “recieve” you typed.",
    );
  });

  it("shows the submitted sentence above its translation", async () => {
    await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.ANSWER_DELIVERY, "Streaming answers");
    entries.value = [{
      entry_id: "entry-1",
      word: "Er steht jeden Morgen um sechs auf.",
      language: "Deutsch",
      status: "done",
      shape: "text",
      text: "Он встаёт каждое утро в шесть.",
      card_status: "text",
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    // A dictionary article opens with its own headword; a translation shows nothing
    // of what was asked unless the entry carries it.
    expect(wrapper.find(".entry-source").text()).toBe("Er steht jeden Morgen um sechs auf.");
    const html = wrapper.html();
    expect(html.indexOf("entry-source")).toBeLessThan(html.indexOf("entry-text"));
  });

  it("leaves a unit answer to open with its own headword", async () => {
    await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.ANSWER_DELIVERY, "Streaming answers");
    entries.value = [{
      entry_id: "entry-1",
      word: "aufstehen",
      language: "Deutsch",
      status: "done",
      shape: "unit",
      text: "<b>aufstehen</b> — вставать",
      card_status: "added",
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-source").exists()).toBe(false);
  });



  it("gives all four card kinds distinct localized status labels", async () => {
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
      "✅ 4 cards: word → meaning, meaning → word, sentence → meaning, gap → word",
    );

    locale.value = "ru";
    await flushPromises();

    expect(wrapper.find(".entry-card-status").text()).toBe(
      "✅ 4 карточки: слово → значение, значение → слово, предложение → значение, пропуск → слово",
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
    expect(wrapper.find(".entry-card-status").text()).toBe(
      "✅ added to Anki · 🔇 submitted text has no audio",
    );

    locale.value = "ru";
    await flushPromises();

    expect(wrapper.find(".entry-card-status").text()).toBe(
      "✅ добавлено в Anki · 🔇 исходный текст без озвучки",
    );
  });

  it("reports missing card audio separately from submitted-text audio", async () => {
    entries.value = [{
      entry_id: "entry-1",
      word: "gave up",
      language: "English",
      status: "done",
      text: "meaning",
      card_status: "added",
      no_audio: false,
      no_card_audio: true,
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".entry-card-status").text()).toBe(
      "✅ added to Anki · 🔇 Anki card has no audio",
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
      expect(wrapper.find(".entry-error .error-text").text()).toBe(
        "Не удалось получить разбор.",
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

  it("documents both lookup shortcuts and what becomes of a misspelling", async () => {
    const wrapper = mount(AddView);
    await flushPromises();

    await wrapper.find(".about-toggle").trigger("click");

    expect(wrapper.find(".about-text").text()).toContain("“? word”");
    expect(wrapper.find(".about-text").text()).toContain("said above the analysis");
    expect(wrapper.find(".about-text").text()).toContain("will not invent a word");
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

  it("offers a failed entry back as a chip instead of asking for it to be retyped", async () => {
    entries.value = [{
      entry_id: "entry-1",
      word: "Ampel",
      lang: "de",
      language: "Deutsch",
      lookup_only: false,
      context: "Die Ampel ist rot.",
      requested_shape: "unit",
      status: "error",
      error: "analysis_failed",
    }];
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") return { entry_id: "entry-2" };
      throw new Error(`Unexpected request: ${path}`);
    });
    const wrapper = mount(AddView);
    await flushPromises();

    await wrapper.find(".entry-error .retry").trigger("click");
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

  it("renders correction, rebuild and detail controls on a finished history entry", async () => {
    entries.value = [{
      entry_id: "entry-1",
      word: "recieve",
      language: "English",
      lookup_only: false,
      status: "done",
      text: "analysis",
      suggestion: "receive",
      detail_available: true,
      model: "free-flash",
      shape: "unit",
      card_status: "added",
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    // The card exists for what was typed, so the control replaces it rather than "corrects".
    expect(wrapper.find(".correction").text()).toContain("Replace the card with “receive”");
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
      "steht auf",
      "fällt aus",
    ]);
    expect(wrapper.find(".segments").text()).toContain("Words and combinations");
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
        word: "steht auf",
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
          reason: "<script>alert(2)</script><b>steht</b>",
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

  it("offers the other senses of a carded word as chips telling them apart", async () => {
    await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.ANSWER_DELIVERY, "Suggested units");
    entries.value = [senseEntry()];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.findAll(".segment-label").map((button) => button.text())).toEqual([
      "bank",
      "bank",
    ]);
    const reasons = wrapper.findAll(".segment-reason").map((node) => node.text());
    expect(reasons).toEqual(["банк", "склон"]);
  });

  it("uses distinct headings for text, expression and sense chips", async () => {
    await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.ANSWER_DELIVERY, "Suggested units");
    entries.value = [senseEntry()];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".segments-title").text()).toBe(
      "Senses of this word — tap one to analyse it:",
    );

    entries.value = [textEntry()];
    await flushPromises();

    expect(wrapper.find(".segments-title").text()).toBe(
      "Words and combinations — tap one to analyse it:",
    );

    entries.value = [{ ...senseEntry(), segment_kind: "expression" }];
    await flushPromises();

    expect(wrapper.find(".segments-title").text()).toBe(
      "Words in this expression — tap one to analyse it:",
    );
  });

  it("keeps the sense chips on a lookup-only answer, heading them without a card", async () => {
    await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.ANSWER_DELIVERY, "Suggested units");
    entries.value = [
      { ...senseEntry(), lookup_only: true, card_status: "lookup_only", card_kinds: [] },
    ];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.findAll(".segment-label")).toHaveLength(2);
    expect(wrapper.find(".segments-title").text()).toBe(
      "Senses of this word — tap one to analyse it:",
    );

    locale.value = "ru";
    await flushPromises();

    expect(wrapper.find(".segments-title").text()).toBe(
      "Значения этого слова — нажмите, чтобы разобрать:",
    );
  });

  it("submits a sense chip with that sense's own sentence as the context", async () => {
    await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.INPUT_AND_LANGUAGES, "Word submission");
    apiRequest.mockImplementation(async (path) => {
      if (path === "/api/languages") return OPTIONS;
      if (path === "/api/words") return { entry_id: "entry-2" };
      throw new Error(`Unexpected request: ${path}`);
    });
    entries.value = [senseEntry()];
    const wrapper = mount(AddView);
    await flushPromises();

    await wrapper.find(".segment-label").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/words", {
      method: "POST",
      body: {
        word: "bank",
        lang: "en",
        lookup_only: false,
        context: "The bank opens at nine.",
        shape: "unit",
        request_id: expect.any(String),
      },
    });
  });

  it("offers neither rebuild nor deeper analysis on a running-text entry", async () => {
    await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.ANSWER_DELIVERY, "Suggested units");
    entries.value = [textEntry()];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".rebuild").exists()).toBe(false);
    expect(wrapper.find(".detail").exists()).toBe(false);
  });

  it("keeps detail but hides rebuild on a lookup-only unit", async () => {
    entries.value = [{
      ...senseEntry(),
      lookup_only: true,
      card_status: "lookup_only",
      card_kinds: [],
      detail_available: true,
    }];
    const wrapper = mount(AddView);
    await flushPromises();

    expect(wrapper.find(".rebuild").exists()).toBe(false);
    expect(wrapper.find(".detail").exists()).toBe(true);
  });
});
