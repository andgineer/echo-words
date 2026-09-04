import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

import { apiRequest } from "../src/api/_request.js";
import { languages, selected } from "../src/composables/useLanguage.js";
import { locale } from "../src/i18n/index.js";
import LanguageDetailView from "../src/views/LanguageDetailView.vue";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

const SERBIAN = {
  code: "sr",
  name: "Српски",
  deck: "EchoWords: Serbian",
  script: "latin+cyrillic",
  dict_api: null,
  tts: "edge",
  tts_voice: null,
  edge_tts_voice: "sr-RS-SophieNeural",
  accent: null,
  api_model: "gpt-fast",
  prompt_hints: "for nouns give gender and plural",
};

const ENGLISH = {
  code: "en",
  name: "English",
  deck: "EchoWords: English",
  script: "latin",
  dict_api: "en",
  tts: "piper",
  tts_voice: "en_US-lessac-medium",
  edge_tts_voice: null,
  accent: "us",
  api_model: null,
  prompt_hints: null,
};

const GERMAN = {
  code: "de",
  name: "Deutsch",
  deck: "EchoWords: German",
  script: "latin",
  dict_api: "de",
  tts: null,
  tts_voice: null,
  edge_tts_voice: null,
  accent: null,
  api_model: null,
  prompt_hints: null,
};

const POLISH = {
  code: "pl",
  name: "Polski",
  deck: "EchoWords: Polish",
  script: "latin",
  dict_api: null,
  tts: null,
  tts_voice: null,
  edge_tts_voice: null,
  accent: null,
  api_model: null,
  prompt_hints: null,
};

const BULGARIAN = {
  code: "bg",
  name: "Български",
  deck: "EchoWords: Bulgarian",
  script: "cyrillic",
  dict_api: null,
  tts: null,
  tts_voice: null,
  edge_tts_voice: null,
  accent: null,
  api_model: null,
  prompt_hints: null,
};

const ITALIAN = {
  code: "it",
  name: "Italiano",
  deck: "EchoWords: Italian",
  script: "latin",
  dict_api: "it",
  tts: "piper",
  tts_voice: "it_IT-riccardo-x_low",
  edge_tts_voice: null,
  accent: null,
  api_model: null,
  prompt_hints: null,
};

beforeEach(async () => {
  await labelBehavior(
    EPIC.APPLICATION_PLATFORM,
    FEATURE.CONFIGURATION_AND_LIFECYCLE,
    "Language editor",
  );
  locale.value = "en";
  languages.value = [];
  selected.value = "";
  localStorage.clear();
  apiRequest.mockReset();
  apiRequest.mockImplementation(serving);
});

const CATALOG = [
  {
    code: "en",
    name: "English",
    english: "English",
    russian: "английский",
    script: "latin",
    piper_voices: ["en_US-lessac-medium"],
    answers: "vouched",
  },
  {
    code: "sr",
    name: "Српски",
    english: "Serbian",
    russian: "сербский",
    script: "latin+cyrillic",
    piper_unusable: true,
    piper_voices: [],
    answers: "vouched",
  },
  {
    code: "de",
    name: "Deutsch",
    english: "German",
    russian: "немецкий",
    script: "latin",
    piper_voices: ["de_DE-thorsten-medium"],
    answers: "vouched",
  },
  {
    code: "pl",
    name: "Polski",
    english: "Polish",
    russian: "польский",
    script: "latin",
    piper_voices: [],
    answers: "unmeasured",
  },
  {
    code: "bg",
    name: "Български",
    english: "Bulgarian",
    russian: "болгарский",
    script: "cyrillic",
    piper_voices: [],
    answers: "unreliable",
  },
  {
    code: "it",
    name: "Italiano",
    english: "Italian",
    russian: "итальянский",
    script: "latin",
    piper_voices: [],
    answers: "unmeasured",
  },
];

async function serving(path, init) {
  if (path === "/api/languages/catalog") return CATALOG;
  if (path === "/api/languages/config")
    return [ENGLISH, GERMAN, SERBIAN, POLISH, BULGARIAN, ITALIAN];
  if (path === "/api/languages") return [{ code: "en", name: "English" }];
  if (path.startsWith("/api/languages/") && init?.method) return { code: path.slice(15) };
  throw new Error(`Unexpected request: ${path}`);
}

afterEach(() => {
  vi.restoreAllMocks();
  locale.value = "en";
  localStorage.clear();
});

async function open(code = "sr") {
  const wrapper = mount(LanguageDetailView, { props: { code } });
  await flushPromises();
  return wrapper;
}

describe("LanguageDetailView", () => {
  it("fills every field the editor shows from the stored language", async () => {
    const wrapper = await open("en");
    await wrapper.get('[data-testid="advanced"]').trigger("click");

    // The name is the directory's, so it is shown and not offered for editing.
    expect(wrapper.get("h2").text()).toBe("English");
    expect(wrapper.find("#lang-name").exists()).toBe(false);
    expect(wrapper.get("#lang-deck").element.value).toBe("EchoWords: English");
    // The script is the directory's too, and shown as the fact it is.
    expect(wrapper.get('[data-testid="script"]').text()).toBe("Latin");
    expect(wrapper.find(".seg-container [data-testid^='script-']").exists()).toBe(false);
    expect(wrapper.get('[data-testid="tts-piper"]').classes()).toContain("active");
    expect(wrapper.get('[data-testid="voice-en_US-lessac-medium"]').classes()).toContain(
      "active",
    );
    expect(wrapper.get("#lang-dict").element.value).toBe("en");
    expect(wrapper.get("#lang-accent").element.value).toBe("us");
  });

  // A prompt fragment is part of what the model is asked, and a change to it would
  // degrade every future answer with nothing to catch it; `api_model` builds the
  // broker's direct map at startup. Both stay a languages.toml edit.
  it("shows none of the fields the directory or the file owns, and sends none", async () => {
    const wrapper = await open();
    await wrapper.get('[data-testid="advanced"]').trigger("click");

    expect(wrapper.html()).not.toContain("for nouns give gender");
    expect(wrapper.html()).not.toContain("gpt-fast");
    expect(wrapper.find("#lang-prompt-hints").exists()).toBe(false);
    expect(wrapper.find("#lang-api-model").exists()).toBe(false);

    await wrapper.get(".btn-save").trigger("click");
    await flushPromises();

    const sent = apiRequest.mock.calls.find(([, init]) => init?.method === "PUT")[1].body;
    expect(Object.keys(sent).sort()).toEqual([
      "accent",
      "deck",
      "dict_api",
      "edge_tts_voice",
      "tts",
      "tts_voice",
    ]);
  });

  it("saves every edited field back under the language's own code", async () => {
    const wrapper = await open();
    await wrapper.get('[data-testid="advanced"]').trigger("click");
    await wrapper.get("#lang-deck").setValue("Serbian::Vocabulary");
    await wrapper.get("#lang-voice").setValue("sr-RS-NicholasNeural");
    await wrapper.get("#lang-accent").setValue("ekavian");

    await wrapper.get(".btn-save").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/languages/sr", {
      method: "PUT",
      body: {
        deck: "Serbian::Vocabulary",
        tts: "edge",
        tts_voice: "",
        edge_tts_voice: "sr-RS-NicholasNeural",
        dict_api: "",
        accent: "ekavian",
      },
    });
    expect(wrapper.get(".saved").text()).toBe("Saved.");
  });

  it("offers the Piper voices it can install and a text box for Edge", async () => {
    const wrapper = await open("en");
    await wrapper.get('[data-testid="advanced"]').trigger("click");
    // Piper reaches the server only as one of the app's own downloads, so the value is
    // picked rather than typed.
    expect(wrapper.find("#lang-voice").exists()).toBe(false);
    expect(wrapper.get('[data-testid="voice-en_US-lessac-medium"]').classes()).toContain(
      "active",
    );

    await wrapper.get('[data-testid="tts-edge"]').trigger("click");

    expect(wrapper.get("label[for='lang-voice']").text()).toBe("Edge voice");
    expect(wrapper.get("#lang-voice").element.value).toBe("");

    await wrapper.get("#lang-voice").setValue("en-US-AriaNeural");
    await wrapper.get('[data-testid="tts-piper"]').trigger("click");

    // The other engine's voice was kept, not overwritten.
    expect(wrapper.get('[data-testid="voice-en_US-lessac-medium"]').classes()).toContain(
      "active",
    );
    await wrapper.get('[data-testid="tts-edge"]').trigger("click");
    expect(wrapper.get("#lang-voice").element.value).toBe("en-US-AriaNeural");
  });

  // Which languages Piper's model actually voices is the directory's to know.
  it("closes Piper off, and says why, where the directory has no voice for it", async () => {
    const wrapper = await open();
    await wrapper.get('[data-testid="advanced"]').trigger("click");

    expect(wrapper.get('[data-testid="tts-piper"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get(".no-piper").text()).toContain("speaks another one");

    await wrapper.get('[data-testid="tts-piper"]').trigger("click");

    expect(wrapper.get('[data-testid="tts-edge"]').classes()).toContain("active");
  });

  // A voice reaches the server only as one of its own pinned downloads, so Piper for a
  // language it ships none for is a promise of a download that never happens.
  it("closes Piper off where this build ships no voice for the language", async () => {
    const wrapper = await open("pl");
    await wrapper.get('[data-testid="advanced"]').trigger("click");

    expect(wrapper.get('[data-testid="tts-piper"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get(".no-piper").text()).toContain("ships no Piper voice");
  });

  // The backend keeps accepting a voice already in the file, because it may have been
  // installed by hand; the screen has to agree, or it locks the language out of the
  // engine it is speaking with.
  it("keeps Piper open for a language voiced by hand that this build ships none for", async () => {
    const wrapper = await open("it");
    await wrapper.get('[data-testid="advanced"]').trigger("click");

    expect(wrapper.get('[data-testid="tts-piper"]').classes()).toContain("active");
    expect(wrapper.find(".no-piper").exists()).toBe(false);
    expect(wrapper.get(".voice-hint").text()).toContain("it_IT-riccardo-x_low");

    await wrapper.get('[data-testid="tts-edge"]').trigger("click");

    expect(wrapper.get('[data-testid="tts-piper"]').attributes("disabled")).toBeUndefined();

    await wrapper.get('[data-testid="tts-piper"]').trigger("click");

    expect(wrapper.get('[data-testid="tts-piper"]').classes()).toContain("active");
  });

  it("names the voice it would install for a language this build carries one for", async () => {
    const wrapper = await open("en");
    await wrapper.get('[data-testid="advanced"]').trigger("click");

    expect(wrapper.get('[data-testid="tts-piper"]').classes()).toContain("active");
    expect(wrapper.get('[data-testid="tts-piper"]').attributes("disabled")).toBeUndefined();
    expect(wrapper.find(".no-piper").exists()).toBe(false);
    expect(wrapper.get(".voice-hint").classes()).not.toContain("warn");
    expect(wrapper.get(".voice-hint").text()).toContain("en_US-lessac-medium");
  });

  it("fills in the voice the server would install when Piper is chosen", async () => {
    const wrapper = await open("de");
    await wrapper.get('[data-testid="advanced"]').trigger("click");
    expect(wrapper.find('[data-testid="voice-de_DE-thorsten-medium"]').exists()).toBe(false);

    await wrapper.get('[data-testid="tts-piper"]').trigger("click");

    expect(wrapper.get('[data-testid="voice-de_DE-thorsten-medium"]').classes()).toContain(
      "active",
    );
  });

  // The three the bench is built on are the three the reader may take at face value.
  it("says what has been measured about this language's answers", async () => {
    const measured = await open("en");
    expect(measured.find(".answers-note").exists()).toBe(false);

    const wrapper = await open("pl");

    expect(wrapper.get(".answers-note").text()).toContain("has been measured against");
    expect(wrapper.get(".answers-note").classes()).not.toContain("warn");

    // Measured and refused is not the same as unmeasured, and it is said louder.
    const refused = await open("bg");

    expect(refused.get(".answers-note").text()).toContain("most answers in this language");
    expect(refused.get(".answers-note").classes()).toContain("warn");
  });

  it("keeps the voice, dictionary and accent behind Advanced", async () => {
    const wrapper = await open();

    expect(wrapper.find("#lang-voice").exists()).toBe(false);
    expect(wrapper.find("#lang-dict").exists()).toBe(false);
    expect(wrapper.get("#lang-deck").exists()).toBe(true);
  });

  it("asks before removing the language, and says the cards stay", async () => {
    const wrapper = await open();

    await wrapper.get(".remove").trigger("click");

    expect(wrapper.get(".confirm-text").text()).toBe(
      "Remove “Српски”? Its cards stay in Anki.",
    );
    expect(apiRequest.mock.calls.filter(([, init]) => init?.method === "DELETE")).toEqual([]);

    await wrapper.get(".confirm-yes").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/languages/sr", { method: "DELETE" });
    // And the words screen is told, since the removed language may have been selected.
    expect(apiRequest).toHaveBeenCalledWith("/api/languages");
    expect(wrapper.emitted("done")).toHaveLength(1);
  });

  it("shows the backend's refusal instead of claiming a save", async () => {
    apiRequest.mockImplementation(async (path, init) => {
      if (init?.method === "PUT") throw new Error("Fill in: deck.");
      return serving(path, init);
    });
    const wrapper = await open();
    await wrapper.get("#lang-deck").setValue("");

    await wrapper.get(".btn-save").trigger("click");
    await flushPromises();

    expect(wrapper.get(".hint").text()).toBe("Fill in: deck.");
    expect(wrapper.find(".saved").exists()).toBe(false);
  });

  it("returns to the list when the language it was opened for is gone", async () => {
    const wrapper = await open("fr");

    expect(wrapper.emitted("done")).toHaveLength(1);
  });

  it("goes back to the list", async () => {
    const wrapper = await open();

    await wrapper.get(".back").trigger("click");

    expect(wrapper.emitted("back")).toHaveLength(1);
  });
});
