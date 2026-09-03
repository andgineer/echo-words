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

  it("shows the deck a typed name will get, before anything is sent", async () => {
    const wrapper = await open();

    expect(wrapper.get(".deck-hint").text()).toContain("named after the language");

    await wrapper.get("#new-lang").setValue("Español");

    expect(wrapper.get(".deck-hint").text()).toBe(
      "The deck “EchoWords: Español” is created for it. " +
        "Script, voice and dictionary can be set afterwards.",
    );
  });

  it("adds a language under the code taken from its name, with the derived deck", async () => {
    const wrapper = await open();
    await wrapper.get("#new-lang").setValue("Español");

    await wrapper.get(".add").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/languages/es", {
      method: "PUT",
      body: { name: "Español", deck: "EchoWords: Español", script: "latin" },
    });
    expect(wrapper.get("#new-lang").element.value).toBe("");
  });

  it("takes a short entry as the code itself", async () => {
    const wrapper = await open();
    await wrapper.get("#new-lang").setValue("fr");

    await wrapper.get(".add").trigger("click");
    await flushPromises();

    expect(apiRequest).toHaveBeenCalledWith("/api/languages/fr", {
      method: "PUT",
      body: { name: "fr", deck: "EchoWords: fr", script: "latin" },
    });
  });

  it("sends nothing for an empty field", async () => {
    const wrapper = await open();

    await wrapper.get(".add").trigger("click");
    await flushPromises();

    expect(apiRequest.mock.calls.filter(([, init]) => init?.method === "PUT")).toEqual([]);
  });

  it("shows the backend's refusal of a bad entry", async () => {
    apiRequest.mockImplementation(async (path, init) => {
      if (init?.method === "PUT") throw new Error("“ES1” is not a language code.");
      return serving(TABLE)(path, init);
    });
    const wrapper = await open();
    await wrapper.get("#new-lang").setValue("Español");

    await wrapper.get(".add").trigger("click");
    await flushPromises();

    expect(wrapper.get(".hint").text()).toBe("“ES1” is not a language code.");
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
