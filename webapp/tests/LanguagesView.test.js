import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../src/api/_request.js", () => ({ apiRequest: vi.fn() }));

import { apiRequest } from "../src/api/_request.js";
import { languages, selected } from "../src/composables/useLanguage.js";
import { locale } from "../src/i18n/index.js";
import LanguagesView from "../src/views/LanguagesView.vue";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

const TABLE = [
  { code: "sr", name: "Српски", deck: "EchoWords: Serbian", script: "latin+cyrillic" },
  { code: "de", name: "Deutsch", deck: "EchoWords: German", script: "latin" },
];

// The directory the search runs over: the code and the name are its to give, never
// the reader's to type.
const CATALOG = [
  {
    code: "de",
    name: "Deutsch",
    english: "German",
    russian: "немецкий",
    script: "latin",
    deck: "EchoWords: German",
    dict_api: "de",
    answers: "vouched",
  },
  {
    code: "es",
    name: "Español",
    english: "Spanish",
    russian: "испанский",
    script: "latin",
    deck: "EchoWords: Spanish",
    dict_api: "es",
    answers: "unmeasured",
  },
  {
    code: "ru",
    name: "Русский",
    english: "Russian",
    russian: "русский",
    script: "cyrillic",
    deck: "EchoWords: Russian",
    dict_api: "ru",
  },
  {
    code: "be",
    name: "Беларуская",
    english: "Belarusian",
    russian: "белорусский",
    script: "cyrillic",
    deck: "EchoWords: Belarusian",
    dict_api: null,
    answers: "unreliable",
  },
];

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
  apiRequest.mockImplementation(serving(TABLE));
});

// The backend the editor talks to: the whole table, the slim list the rest of the app
// reads, and the writes, which the caller re-reads both of the others after.
function serving(table) {
  return async (path, init) => {
    if (path === "/api/languages/catalog") return CATALOG;
    if (path === "/api/languages/config") return table;
    if (path === "/api/languages") return table.map(({ code, name }) => ({ code, name }));
    if (path.startsWith("/api/languages/") && init?.method) return { code: path.slice(15) };
    throw new Error(`Unexpected request: ${path}`);
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  locale.value = "en";
  localStorage.clear();
});

async function open() {
  const wrapper = mount(LanguagesView);
  await flushPromises();
  return wrapper;
}

describe("LanguagesView", () => {
  it("lists every configured language with its code and deck", async () => {
    const wrapper = await open();

    expect(wrapper.findAll(".lang-name").map((node) => node.text())).toEqual([
      "Српскиsr",
      "Deutschde",
    ]);
    expect(wrapper.findAll(".lang-deck").map((node) => node.text())).toEqual([
      "EchoWords: Serbian",
      "EchoWords: German",
    ]);
  });

  it("opens the settings of the language whose pencil was pressed", async () => {
    const wrapper = await open();

    await wrapper.get('[data-testid="open-de"]').trigger("click");

    expect(wrapper.emitted("open")).toEqual([["de"]]);
  });

  it("goes back to the words", async () => {
    const wrapper = await open();

    await wrapper.get(".back").trigger("click");

    expect(wrapper.emitted("back")).toHaveLength(1);
  });

  // Never a modal: the question replaces the row it came from.
  it("asks inside the row before removing, and removes nothing until confirmed", async () => {
    const wrapper = await open();

    await wrapper.get('[data-testid="remove-de"]').trigger("click");

    expect(wrapper.get(".confirm-text").text()).toBe(
      "Remove “Deutsch”? Its cards stay in Anki.",
    );
    expect(apiRequest.mock.calls.filter(([, init]) => init?.method === "DELETE")).toEqual([]);

    await wrapper.get(".confirm-yes").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/languages/de", { method: "DELETE" });
  });

  it("calls nothing when the question is declined", async () => {
    const wrapper = await open();

    await wrapper.get('[data-testid="remove-de"]').trigger("click");
    await wrapper.get(".confirm-no").trigger("click");
    await flushPromises();

    expect(apiRequest.mock.calls.filter(([, init]) => init?.method === "DELETE")).toEqual([]);
    expect(wrapper.find('[data-testid="remove-de"]').exists()).toBe(true);
  });

  it("refuses to leave the app without a language, and says why", async () => {
    apiRequest.mockImplementation(async (path, init) => {
      if (init?.method === "DELETE") {
        throw new Error("This is the only language left; the app cannot run without one.");
      }
      return serving(TABLE)(path, init);
    });
    const wrapper = await open();

    await wrapper.get('[data-testid="remove-de"]').trigger("click");
    await wrapper.get(".confirm-yes").trigger("click");
    await flushPromises();

    expect(wrapper.get(".hint").text()).toContain("cannot run without one");
  });

  it("offers nothing until something is typed, and says so when nothing matches", async () => {
    const wrapper = await open();

    expect(wrapper.findAll(".match")).toEqual([]);
    expect(wrapper.find(".no-matches").exists()).toBe(false);
    expect(wrapper.get(".deck-hint").text()).toContain("comes from the directory");

    await wrapper.get("#new-lang").setValue("klingon");

    expect(wrapper.findAll(".match")).toEqual([]);
    expect(wrapper.get(".no-matches").text()).toBe("The directory has no such language.");
  });

  // The reader knows the language by whichever name they know it by.
  it.each([
    ["Español", "es"],
    ["Spanish", "es"],
    ["испанский", "es"],
    ["es", "es"],
  ])("finds a language searched for as %s", async (query, code) => {
    const wrapper = await open();

    await wrapper.get("#new-lang").setValue(query);

    expect(wrapper.findAll(".match-name").map((node) => node.text())).toContain(
      `Español${code}`,
    );
  });

  // The code addresses the wikis and the audio cache, and the name is what the prompt
  // calls the source language: both come from the row, not from the typing.
  it("adds the language whose row was pressed, under the directory's own code", async () => {
    const wrapper = await open();
    await wrapper.get("#new-lang").setValue("Spanish");

    await wrapper.get('[data-testid="add-es"]').trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/languages/es", {
      method: "PUT",
      body: { deck: "EchoWords: Spanish", dict_api: "es" },
    });
    expect(wrapper.get("#new-lang").element.value).toBe("");
  });

  // A fluent answer in an unmeasured language reads like a measured one, so the row
  // says what is known before the language is added rather than after.
  it("says of each offered language what has been measured about its answers", async () => {
    const wrapper = await open();

    await wrapper.get("#new-lang").setValue("es");
    expect(wrapper.get('[data-testid="add-es"]').text()).toContain("not measured");
    expect(wrapper.get(".match-answers").classes()).not.toContain("warn");

    await wrapper.get("#new-lang").setValue("be");
    expect(wrapper.get('[data-testid="add-be"]').text()).toContain("measured — unreliable");
    expect(wrapper.get(".match-answers").classes()).toContain("warn");
  });

  it("leaves out a language that is already configured", async () => {
    const wrapper = await open();

    await wrapper.get("#new-lang").setValue("de");

    expect(wrapper.find('[data-testid="add-de"]').exists()).toBe(false);
  });

  it("offers a name the query opens before one that merely contains it", async () => {
    const wrapper = await open();

    await wrapper.get("#new-lang").setValue("ru");

    expect(wrapper.findAll(".match-name").map((node) => node.text())).toEqual([
      "Русскийru",
      "Беларускаяbe",
    ]);
  });

  it("shows the backend's refusal of a language it will not write", async () => {
    apiRequest.mockImplementation(async (path, init) => {
      if (init?.method === "PUT") throw new Error("Fill in: deck.");
      return serving(TABLE)(path, init);
    });
    const wrapper = await open();
    await wrapper.get("#new-lang").setValue("Español");

    await wrapper.get('[data-testid="add-es"]').trigger("click");
    await flushPromises();

    expect(wrapper.get(".hint").text()).toBe("Fill in: deck.");
  });

  // A removed language may have been the one selected on the words screen.
  it("reloads the language row after every write, replacing a stale selection", async () => {
    selected.value = "de";
    const wrapper = await open();
    apiRequest.mockImplementation(serving(TABLE.filter((row) => row.code !== "de")));

    await wrapper.get('[data-testid="remove-de"]').trigger("click");
    await wrapper.get(".confirm-yes").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/languages");
    expect(languages.value).toEqual([{ code: "sr", name: "Српски" }]);
    expect(selected.value).toBe("sr");
    expect(wrapper.findAll(".lang-name")).toHaveLength(1);
  });
});
