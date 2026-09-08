import { createApp } from "vue";
import App from "./App.vue";
import { initializeCache, requestPersistentStorage } from "./api/cache.js";
import { restoreEntries } from "./composables/useEntries.js";
import { restoreLanguages } from "./composables/useLanguage.js";
import "./assets/base.css";

async function start() {
  await initializeCache();
  restoreEntries();
  restoreLanguages();
  createApp(App).mount("#app");
  requestPersistentStorage();
}

void start();
