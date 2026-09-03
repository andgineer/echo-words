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

async function serving(path, init) {
  if (path === "/api/languages/config") return [ENGLISH, SERBIAN];
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

    expect(wrapper.get("#lang-name").element.value).toBe("English");
    expect(wrapper.get("#lang-deck").element.value).toBe("EchoWords: English");
    expect(wrapper.get('[data-testid="script-latin"]').classes()).toContain("active");
    expect(wrapper.get('[data-testid="tts-piper"]').classes()).toContain("active");
    expect(wrapper.get("#lang-voice").element.value).toBe("en_US-lessac-medium");
    expect(wrapper.get("#lang-dict").element.value).toBe("en");
    expect(wrapper.get("#lang-accent").element.value).toBe("us");
  });

  // A prompt fragment is part of what the model is asked, and a change to it would
  // degrade every future answer with nothing to catch it; `api_model` builds the
  // broker's direct map at startup. Both stay a languages.toml edit.
  it("shows neither the prompt hint nor the paid model, and sends neither", async () => {
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
      "name",
      "script",
      "tts",
      "tts_voice",
    ]);
  });

  it("saves every edited field back under the language's own code", async () => {
    const wrapper = await open();
    await wrapper.get('[data-testid="advanced"]').trigger("click");
    await wrapper.get("#lang-name").setValue("Serbian");
    await wrapper.get("#lang-deck").setValue("Serbian::Vocabulary");
    await wrapper.get('[data-testid="script-cyrillic"]').trigger("click");
    await wrapper.get("#lang-voice").setValue("sr-RS-NicholasNeural");
    await wrapper.get("#lang-accent").setValue("ekavian");

    await wrapper.get(".btn-save").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/languages/sr", {
      method: "PUT",
      body: {
        name: "Serbian",
        deck: "Serbian::Vocabulary",
        script: "cyrillic",
        tts: "edge",
        tts_voice: "",
        edge_tts_voice: "sr-RS-NicholasNeural",
        dict_api: "",
        accent: "ekavian",
      },
    });
    expect(wrapper.get(".saved").text()).toBe("Saved.");
  });

  it("binds the voice field to whichever engine is chosen", async () => {
    const wrapper = await open("en");
    await wrapper.get('[data-testid="advanced"]').trigger("click");
    expect(wrapper.get("label[for='lang-voice']").text()).toBe("Piper voice");
    expect(wrapper.get("#lang-voice").element.value).toBe("en_US-lessac-medium");

    await wrapper.get('[data-testid="tts-edge"]').trigger("click");

    expect(wrapper.get("label[for='lang-voice']").text()).toBe("Edge voice");
    expect(wrapper.get("#lang-voice").element.value).toBe("");

    await wrapper.get("#lang-voice").setValue("en-US-AriaNeural");
    await wrapper.get('[data-testid="tts-piper"]').trigger("click");

    // The other engine's voice was kept, not overwritten.
    expect(wrapper.get("#lang-voice").element.value).toBe("en_US-lessac-medium");
  });

  // Piper's only sr_RS model is Lower Sorbian, so it would speak another language.
  it("warns that Piper has no Serbian voice", async () => {
    const wrapper = await open();
    await wrapper.get('[data-testid="advanced"]').trigger("click");
    expect(wrapper.get(".voice-hint").text()).toContain("fetched with the first word");

    await wrapper.get('[data-testid="tts-piper"]').trigger("click");

    expect(wrapper.get(".voice-hint").classes()).toContain("warn");
    expect(wrapper.get(".voice-hint").text()).toContain("Lower Sorbian");
  });

  it("keeps the voice, dictionary and accent behind Advanced", async () => {
    const wrapper = await open();

    expect(wrapper.find("#lang-voice").exists()).toBe(false);
    expect(wrapper.find("#lang-dict").exists()).toBe(false);
    expect(wrapper.get("#lang-name").exists()).toBe(true);
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
