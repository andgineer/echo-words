import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import EntryCard from "../src/components/EntryCard.vue";
import { locale } from "../src/i18n/index.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

function card(entry, props = {}) {
  return mount(EntryCard, { props: { entry, ...props } });
}

function textEntry(
  segments = [
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
  ],
) {
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
      { label: "bank", reason: "склон", context: "The bank of the hill is steep." },
    ],
  };
}

beforeEach(async () => {
  await labelBehavior(EPIC.VOCABULARY_ANALYSIS, FEATURE.ANSWER_DELIVERY, "The entry card");
  locale.value = "en";
});

afterEach(() => {
  locale.value = "en";
});

describe("EntryCard", () => {
  it("heads a word entry with the word and the model that answered", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "прозор",
      lang: "sr",
      status: "done",
      shape: "unit",
      text: "окно",
      model: "gemini-2.5-flash",
      card_status: "added",
    });

    expect(wrapper.get(".entry-title").text()).toBe("прозор");
    expect(wrapper.get(".entry-title").classes()).toContain("word");
    expect(wrapper.get(".entry-model").text()).toBe("gemini-2.5-flash");
    // The language is named by the button row above the screen, and the card status
    // says what became of the card: the old meta line repeated both.
    expect(wrapper.find(".entry-meta").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Serbian");
  });

  it("heads a running-text entry with its kind instead of the whole sentence", () => {
    const wrapper = card(textEntry());

    expect(wrapper.get(".entry-title").text()).toBe("Sentence");
    expect(wrapper.get(".entry-title").classes()).toContain("kind");
    expect(wrapper.get(".entry-source").text()).toBe("Er steht jeden Morgen um sechs auf.");
    const html = wrapper.html();
    expect(html.indexOf("entry-source")).toBeLessThan(html.indexOf("entry-text"));
  });

  it("says no model while the answer is still coming", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "Word",
      lang: "en",
      status: "pending",
      text: "<b>Word</b> — meaning",
    });

    expect(wrapper.find(".entry-model").exists()).toBe(false);
    expect(wrapper.get(".entry-text").html()).toContain("<b>Word</b> — meaning");
  });

  // Decision 4: the tap has to be answered before the network is.
  it("shows the progress strip and how long it takes while an entry is pending", () => {
    const wrapper = card({ entry_id: "entry-1", word: "прозор", lang: "sr", status: "pending" });

    expect(wrapper.find(".progress").exists()).toBe(true);
    expect(wrapper.get(".working").text()).toBe("Analysing “прозор” — usually a couple of seconds");
  });

  it("says the paid call is running from the moment it is asked for", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "прозор",
      lang: "sr",
      status: "done",
      shape: "unit",
      text: "окно",
      card_status: "added",
      detail_available: true,
      detail_pending: true,
    });

    expect(wrapper.find(".progress").exists()).toBe(true);
    expect(wrapper.get(".working").text()).toBe(
      "Building the full entry — usually about 10 seconds",
    );
    // Nothing to press while it runs.
    expect(wrapper.find(".entry-actions").exists()).toBe(false);
  });

  it("shows the Anki result attached to a completed answer", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    const wrapper = card({
      entry_id: "entry-1",
      word: "Word",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "<b>Word</b> — meaning",
      card_status: "added",
    });

    expect(wrapper.get(".entry-card-status").text()).toBe("✅ added to Anki");
  });

  it("gives all four card kinds distinct localized status labels", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    const wrapper = card(senseEntry());

    expect(wrapper.get(".entry-card-status").text()).toBe(
      "✅ 4 cards: word → meaning, meaning → word, sentence → meaning, gap → word",
    );

    locale.value = "ru";
    await wrapper.vm.$nextTick();

    expect(wrapper.get(".entry-card-status").text()).toBe(
      "✅ 4 карточки: слово → значение, значение → слово, предложение → значение, пропуск → слово",
    );
  });

  it("falls back to the plain result when the kinds are not known", () => {
    const wrapper = card({ ...senseEntry(), card_kinds: [] });

    expect(wrapper.get(".entry-card-status").text()).toBe("✅ added to Anki");
  });

  it("reports missing card audio separately from submitted-text audio", () => {
    const withNoAudio = card({ ...senseEntry(), card_kinds: [], no_audio: true });
    expect(withNoAudio.get(".entry-card-status").text()).toBe(
      "✅ added to Anki · 🔇 submitted text has no audio",
    );

    const withNoCardAudio = card({ ...senseEntry(), card_kinds: [], no_card_audio: true });
    expect(withNoCardAudio.get(".entry-card-status").text()).toBe(
      "✅ added to Anki · 🔇 Anki card has no audio",
    );
  });

  it("shows an Anki failure reason verbatim, and a failed analysis in the interface language",
    async () => {
      await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
      locale.value = "ru";
      const failedCard = card({
        entry_id: "entry-1",
        word: "Word",
        lang: "en",
        status: "done",
        shape: "unit",
        text: "meaning",
        card_status: "failed",
        card_error: "note type EchoWords is misconfigured",
      });
      expect(failedCard.get(".entry-card-status").text()).toBe(
        "⚠️ note type EchoWords is misconfigured",
      );

      const failedAnalysis = card({
        entry_id: "entry-2",
        word: "Other",
        lang: "en",
        status: "error",
        error: "analysis_failed",
      });
      expect(failedAnalysis.get(".entry-error .error-text").text()).toBe(
        "Не удалось получить разбор.",
      );
    });

  // A failed entry is an entry like any other, and one card is all there is to show it in.
  it("keeps a failed entry's retry, and the two control errors, inside the card", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "Ampel",
      lang: "de",
      status: "error",
      error: "analysis_failed",
      detail_error: "the paid model refused",
      control_error: "Anki is not reachable",
    });

    expect(wrapper.get(".entry-error .retry").text()).toBe("Send “Ampel” again");
    expect(wrapper.text()).toContain("the paid model refused");
    expect(wrapper.text()).toContain("Anki is not reachable");
  });

  it("words an article that failed on its own, from the code the backend sent", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "Ampel",
      lang: "de",
      detail_error: "detail_failed",
    });

    expect(wrapper.text()).toContain("Could not finish the full entry.");
  });

  it("says nothing about a running text's card, because it never had one", () => {
    const wrapper = card({ ...textEntry(), card_status: "text" });

    expect(wrapper.find(".entry-card-status").exists()).toBe(false);
  });

  it("says which word the card is for when a misspelling was corrected onto it", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
    const wrapper = card({
      entry_id: "entry-1",
      word: "envi",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "<b>envy</b> — зависть",
      card_status: "added",
      card_kinds: ["Recognition"],
      analysed_as: "envy",
      typo_suspected: true,
    });

    expect(wrapper.get(".entry-notice").text()).toBe(
      "“envi” looks like a typo, so the card is for “envy” instead.",
    );
    const html = wrapper.html();
    expect(html.indexOf("entry-notice")).toBeLessThan(html.indexOf("entry-text"));
  });

  it("says nothing about the spelling when the card is for the word as typed", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "receive",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "<b>receive</b> — получать",
      card_status: "added",
      card_kinds: ["Recognition"],
    });

    expect(wrapper.find(".entry-notice").exists()).toBe(false);
  });

  it("shows no card and no article for wording the answer would not vouch for", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "blorptium",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "",
      card_status: "unattested",
    });

    expect(wrapper.get(".entry-notice").text()).toBe(
      "“blorptium” — the model does not vouch for this word. No card was made.",
    );
    expect(wrapper.get(".entry-card-status").text()).toBe("🚫 no card");
    expect(wrapper.find(".entry-text").exists()).toBe(false);
  });

  it("does not tell a lookup that a card was withheld from it", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "blorptium",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "",
      card_status: "unattested",
      lookup_only: true,
    });

    expect(wrapper.get(".entry-notice").text()).toBe(
      "“blorptium” — the model does not vouch for this word.",
    );
  });

  it("sends the reader to a web search for the exact wording, not back to the encyclopedia",
    async () => {
      await labelBehavior(EPIC.ANKI_CARDS, FEATURE.COLLECTION, "Card delivery status");
      const wrapper = card({
        entry_id: "entry-1",
        word: "bookshelfy",
        lang: "en",
        status: "done",
        shape: "unit",
        text: "<b>bookshelfy</b>",
        card_status: "added",
        card_kinds: ["Recognition"],
        not_in_references: true,
        usage_search_url: "https://duckduckgo.com/?q=%22bookshelfy%22",
      });

      const notice = wrapper.get(".entry-notice.unverified");
      expect(notice.text()).toContain("No dictionary has “bookshelfy”");
      expect(notice.get(".usage-search").text()).toBe("Search the web");
      expect(notice.get(".usage-search").attributes("href")).toBe(
        "https://duckduckgo.com/?q=%22bookshelfy%22",
      );
      expect(wrapper.find(".entry-text").exists()).toBe(true);
    });

  it("asks about the word the card carries, not the one that was typed", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "recieve",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "<b>receive</b>",
      card_status: "added",
      analysed_as: "receive",
      not_in_references: true,
    });

    expect(wrapper.get(".entry-notice.unverified").text()).toContain("“receive”");
  });

  it("says nothing when the reference works had the word", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "petrichor",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "<b>petrichor</b>",
      card_status: "added",
      not_in_references: false,
    });

    expect(wrapper.find(".entry-notice.unverified").exists()).toBe(false);
  });

  it("points the offer back once the entry shows the other spelling", async () => {
    await labelBehavior(EPIC.ANKI_CARDS, FEATURE.CORRECTION_AND_DETAIL, "Correction control");
    const wrapper = card({
      entry_id: "entry-1",
      word: "envy",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "<b>envy</b> — зависть",
      card_status: "added",
      card_kinds: ["Recognition"],
      suggestion: "envi",
      showing_other_spelling: true,
    });

    // Calling the learner's own spelling "the usual one" is what the flag prevents.
    expect(wrapper.get(".entry-notice").text()).toContain(
      "This is “envy”, not the “envi” you typed.",
    );
    expect(wrapper.get(".correction").text()).toBe("↩︎ Go back to a card for “envi”");

    await wrapper.get(".correction").trigger("click");
    expect(wrapper.emitted("switch")).toHaveLength(1);
  });

  // Reached after a switch back: the learner returned to their own spelling, this
  // answer accepted it as a word, and the other one stays on offer beside it.
  it("does not call a misspelling a more usual spelling on a lookup", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "recieve",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "<b>recieve</b> — получать",
      card_status: "lookup_only",
      suggestion: "receive",
      typo_suspected: true,
    });

    expect(wrapper.get(".entry-notice").text()).toContain(
      "“recieve” looks like a typo for “receive”",
    );
  });

  it("names the other spelling once the entry is back on the one typed", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "envi",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "<b>envi</b> — зависть",
      card_status: "added",
      card_kinds: ["Recognition"],
      suggestion: "envy",
    });

    expect(wrapper.get(".entry-notice").text()).toContain(
      "The card is for “envi”; “envy” is named the more usual spelling.",
    );
    expect(wrapper.get(".correction").text()).toBe("Replace the card with “envy”");
  });

  it("names the word a card is for when it is not the word that was typed", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "envi",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "<b>environment</b> — окружающая среда",
      card_status: "added",
      card_kinds: ["Recognition"],
      analysed_as: "environment",
      typo_suspected: false,
    });

    // Saying nothing here is how a learner ends up drilling a word they never typed;
    // calling it a typo is how every inflected submission gets accused of one.
    expect(wrapper.get(".entry-notice").text()).toBe(
      "The card is for “environment”, not the “envi” you typed.",
    );
  });

  it("makes no card for a spelling the answer itself called wrong", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "recieve",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "<b>recieve</b> — получать",
      card_status: "misspelled",
      suggestion: "receive",
    });

    expect(wrapper.get(".entry-notice").text()).toContain(
      "“recieve” looks like a typo for “receive”, so no card was made.",
    );
    // There is no card to replace, so the offer says what it will actually do.
    expect(wrapper.get(".correction").text()).toBe("Analyse “receive” instead");
  });

  it("keeps the way back when the switch could not store its card", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "receive",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "<b>receive</b> — получать",
      card_status: "failed",
      card_kept: true,
      suggestion: "recieve",
      showing_other_spelling: true,
    });

    // Without this the entry shows another word than the deck holds, says nothing
    // about it, and leaves retyping as the only way back.
    expect(wrapper.get(".entry-notice").text()).toContain(
      "This is “receive”, not the “recieve” you typed.",
    );
    expect(wrapper.get(".entry-card-status").text()).toContain("the card you had is untouched");
  });

  it("says which word a corrected lookup analysed, though it carded nothing", () => {
    const wrapper = card({
      entry_id: "entry-1",
      word: "recieve",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "<b>receive</b> — получать",
      card_status: "lookup_only",
      analysed_as: "receive",
      typo_suspected: true,
    });

    expect(wrapper.get(".entry-notice").text()).toBe(
      "This is “receive”, not the “recieve” you typed.",
    );
  });

  it("attaches a replayable pronunciation to a completed answer", async () => {
    await labelBehavior(EPIC.PRONUNCIATION, FEATURE.AUDIO_DELIVERY, "Playback");
    const wrapper = card({
      entry_id: "entry-1",
      word: "Word",
      lang: "en",
      status: "done",
      shape: "unit",
      text: "<b>Word</b> — meaning",
      audio_url: "/api/audio/pronunciation-aabbccddeeff00112233.mp3",
    });

    const player = wrapper.get("audio.entry-audio");
    expect(player.attributes("src")).toBe("/api/audio/pronunciation-aabbccddeeff00112233.mp3");
    expect(player.attributes()).toHaveProperty("controls");
    expect(player.attributes()).toHaveProperty("autoplay");
  });

  it("plays the whole text beside the pronunciation of the unit taken from it", async () => {
    await labelBehavior(EPIC.PRONUNCIATION, FEATURE.AUDIO_DELIVERY, "Playback");
    const wrapper = card({
      entry_id: "entry-1",
      word: "aufstehen",
      lang: "de",
      status: "done",
      shape: "unit",
      text: "<b>aufstehen</b> — вставать",
      context: "Er steht jeden Morgen um sechs auf.",
      audio_url: "/api/audio/pronunciation-aabbccddeeff00112233.mp3",
      context_audio_url: "/api/audio/pronunciation-1122334455667788990a.mp3",
    });

    const players = wrapper.findAll("audio.entry-audio");
    expect(players.map((player) => player.attributes("src"))).toEqual([
      "/api/audio/pronunciation-aabbccddeeff00112233.mp3",
      "/api/audio/pronunciation-1122334455667788990a.mp3",
    ]);
    // Two players may not talk over each other: only the unit's own audio starts by itself.
    expect(players[1].attributes()).not.toHaveProperty("autoplay");
    expect(wrapper.get(".context-audio-title").text()).toBe("The whole text");
  });

  it("leaves a text answer with the single player that voices it whole", async () => {
    await labelBehavior(EPIC.PRONUNCIATION, FEATURE.AUDIO_DELIVERY, "Playback");
    const wrapper = card({
      ...textEntry(),
      audio_url: "/api/audio/pronunciation-1122334455667788990a.mp3",
    });

    const players = wrapper.findAll("audio.entry-audio");
    expect(players).toHaveLength(1);
    expect(players[0].attributes()).toHaveProperty("autoplay");
    expect(wrapper.find(".context-audio-title").exists()).toBe(false);
  });

  // Filled pills that look pressable say what a caption read once in a lifetime said.
  it("offers the suggested units as chips with no caption over them", () => {
    const wrapper = card(textEntry());

    expect(wrapper.findAll(".segment-label").map((button) => button.text())).toEqual([
      "steht auf",
      "fällt aus",
    ]);
    expect(wrapper.find(".segments-title").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("tap one to analyse");
  });

  // Every sense of one word carries that same word, so a row of them reads as one
  // button repeated, and what tells them apart sits in the caption underneath.
  it("names a sense chip by its meaning rather than repeating the word", () => {
    const wrapper = card(senseEntry());

    expect(wrapper.findAll(".segment-label").map((button) => button.text())).toEqual([
      "банк",
      "склон",
    ]);
    expect(wrapper.findAll(".segment-reason")).toHaveLength(0);
  });

  it("keeps a phrase's own parts on its chips, where the wording already differs", () => {
    const wrapper = card(textEntry());

    expect(wrapper.findAll(".segment-label").map((button) => button.text())).toEqual([
      "steht auf",
      "fällt aus",
    ]);
  });

  it("emits the chip that was tapped, with its own stored context", async () => {
    const wrapper = card(senseEntry());

    await wrapper.get(".segment-label").trigger("click");

    expect(wrapper.emitted("segment")[0][0]).toEqual({
      label: "bank",
      reason: "банк",
      context: "The bank opens at nine.",
    });
  });

  it("renders a suggested unit as text, so model markup can never become markup", () => {
    const wrapper = card(
      textEntry([
        {
          label: "<img src=x onerror=alert(1)>",
          reason: "<script>alert(2)</script><b>steht</b>",
        },
      ]),
    );

    const segment = wrapper.get(".segment");
    expect(segment.get(".segment-label").text()).toBe("<img src=x onerror=alert(1)>");
    expect(segment.html()).toContain("&lt;img src=x onerror=alert(1)&gt;");
    expect(segment.find("img").exists()).toBe(false);
    expect(segment.find("b").exists()).toBe(false);
    expect(segment.find("script").exists()).toBe(false);
  });

  describe("actions", () => {
    it("offers the full entry and the deletion on a carded word", async () => {
      await labelBehavior(EPIC.ANKI_CARDS, FEATURE.CORRECTION_AND_DETAIL, "Detail control");
      const wrapper = card({ ...senseEntry(), detail_available: true });

      expect(wrapper.get(".detail").text()).toBe("The full entry");
      expect(wrapper.get(".detail").element.disabled).toBe(false);
      expect(wrapper.get(".delete-card").text()).toBe("Delete from Anki");
      // The rebuild control is gone; nothing in the interface rewrites a note.
      expect(wrapper.find(".rebuild").exists()).toBe(false);
    });

    it("says the entry is ready and stops offering it once it has landed", () => {
      const wrapper = card({
        ...senseEntry(),
        detail_available: true,
        detail_html: "<p>the long article</p>",
      });

      expect(wrapper.get(".detail").text()).toBe("The entry is ready");
      expect(wrapper.get(".detail").element.disabled).toBe(true);
      expect(wrapper.get(".entry-detail").html()).toContain("the long article");
    });

    // Every finished word answer can be gone deeper on; only a card can be deleted.
    it("keeps the full entry on a lookup that carded nothing, and offers no deletion", () => {
      const wrapper = card({
        ...senseEntry(),
        lookup_only: true,
        card_status: "lookup_only",
        card_kinds: [],
        detail_available: true,
      });

      expect(wrapper.find(".detail").exists()).toBe(true);
      expect(wrapper.find(".delete-card").exists()).toBe(false);
    });

    it("offers neither on a running-text entry", () => {
      const wrapper = card(textEntry());

      expect(wrapper.find(".detail").exists()).toBe(false);
      expect(wrapper.find(".delete-card").exists()).toBe(false);
    });

    it("offers the deletion over a note the last answer left standing", () => {
      const wrapper = card({
        ...senseEntry(),
        card_status: "failed",
        card_kept: true,
        card_kinds: [],
      });

      expect(wrapper.find(".delete-card").exists()).toBe(true);
    });

    it("stops offering the deletion once the cards are gone", () => {
      const wrapper = card({ ...senseEntry(), card_status: "deleted", card_kinds: [] });

      expect(wrapper.get(".entry-card-status").text()).toBe("🗑 cards deleted from Anki");
      expect(wrapper.find(".delete-card").exists()).toBe(false);
      expect(wrapper.find(".detail").exists()).toBe(true);
    });

    // Never a modal and never a confirm(): the question replaces the row it came from.
    it("asks inside the card before deleting, and deletes nothing until confirmed", async () => {
      const wrapper = card({ ...senseEntry(), detail_available: true });

      await wrapper.get(".delete-card").trigger("click");

      expect(wrapper.get(".confirm-text").text()).toBe(
        "Delete the cards for “bank” from Anki? The analysis stays on the screen.",
      );
      expect(wrapper.find(".entry-actions").exists()).toBe(false);
      expect(wrapper.emitted("delete-card")).toBeUndefined();

      await wrapper.get(".confirm-yes").trigger("click");

      expect(wrapper.emitted("delete-card")).toHaveLength(1);
      expect(wrapper.find(".confirm").exists()).toBe(false);
      expect(wrapper.find(".entry-actions").exists()).toBe(true);
    });

    it("puts the actions back when the question is declined", async () => {
      const wrapper = card({ ...senseEntry(), detail_available: true });

      await wrapper.get(".delete-card").trigger("click");
      await wrapper.get(".confirm-no").trigger("click");

      expect(wrapper.emitted("delete-card")).toBeUndefined();
      expect(wrapper.find(".entry-actions").exists()).toBe(true);
    });

    it("asks for the full entry when it is pressed", async () => {
      const wrapper = card({ ...senseEntry(), detail_available: true });

      await wrapper.get(".detail").trigger("click");

      expect(wrapper.emitted("detail")).toHaveLength(1);
    });
  });

  describe("swiping", () => {
    function swipe(wrapper, distance) {
      const deck = wrapper.get(".deck");
      return deck
        .trigger("pointerdown", { clientX: 200 })
        .then(() => deck.trigger("pointermove", { clientX: 200 + distance }))
        .then(() => deck.trigger("pointerup"));
    }

    it("moves to the next entry when the card is dragged far enough to the left", async () => {
      const wrapper = card(senseEntry());

      await swipe(wrapper, -80);

      expect(wrapper.emitted("swipe")).toEqual([[1]]);
    });

    it("moves back when it is dragged the other way", async () => {
      const wrapper = card(senseEntry());

      await swipe(wrapper, 80);

      expect(wrapper.emitted("swipe")).toEqual([[-1]]);
    });

    it("springs back on a short drag instead of switching", async () => {
      const wrapper = card(senseEntry());

      await swipe(wrapper, -30);

      expect(wrapper.emitted("swipe")).toBeUndefined();
      expect(wrapper.get(".deck").attributes("style")).toContain("translateX(0px)");
    });

    // `touch-action: pan-y` hands a mostly-vertical drag to the page, and the browser
    // says so by cancelling the gesture: committing it would switch the card under a
    // reader who was only scrolling.
    it("switches nothing when the browser cancels the gesture", async () => {
      const wrapper = card(senseEntry());
      const deck = wrapper.get(".deck");

      await deck.trigger("pointerdown", { clientX: 200 });
      await deck.trigger("pointermove", { clientX: 100 });
      await deck.trigger("pointercancel");

      expect(wrapper.emitted("swipe")).toBeUndefined();
      expect(deck.attributes("style")).toContain("translateX(0px)");
    });

    // A press on a button inside the card must stay a press.
    it("ignores a drag that starts on a control", async () => {
      const wrapper = card({ ...senseEntry(), detail_available: true });
      const button = wrapper.get(".detail");

      await button.trigger("pointerdown", { clientX: 200 });
      await wrapper.get(".deck").trigger("pointermove", { clientX: 100 });
      await wrapper.get(".deck").trigger("pointerup");

      expect(wrapper.emitted("swipe")).toBeUndefined();
    });
  });
});
