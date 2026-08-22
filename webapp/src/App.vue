<script setup>
import { onMounted, onUnmounted, ref } from "vue";
import { useI18n } from "./i18n/index.js";
import { flushQueue } from "./composables/useResendQueue.js";
import HeaderNav from "./components/HeaderNav.vue";
import AddView from "./views/AddView.vue";
import StatsView from "./views/StatsView.vue";
import StatusView from "./views/StatusView.vue";

const APP_VERSION = typeof __APP_VERSION__ !== "undefined" ? __APP_VERSION__ : "dev";

const { t, locale, locales } = useI18n();
const view = ref("add");

function retryQueuedWords() {
  void flushQueue();
}

onMounted(() => {
  retryQueuedWords();
  window.addEventListener("online", retryQueuedWords);
});

onUnmounted(() => window.removeEventListener("online", retryQueuedWords));
</script>

<template>
  <header class="app-header">
    <h1>
      echo-words
      <span class="header-version">v{{ APP_VERSION }}</span>
    </h1>
    <div class="header-controls">
      <HeaderNav v-model:view="view" />
      <select v-model="locale" class="locale" :aria-label="t('nav.locale')">
        <option v-for="item in locales" :key="item.code" :value="item.code">
          {{ item.label }}
        </option>
      </select>
    </div>
  </header>
  <main class="app-main">
    <AddView v-if="view === 'add'" />
    <StatsView v-else-if="view === 'stats'" />
    <StatusView v-else />
  </main>
</template>

<style scoped>
.app-header {
  background: var(--surface);
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: space-between;
  align-items: center;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.app-header h1 {
  font-size: 1.1rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.header-version {
  font-size: 0.7rem;
  font-weight: 400;
  letter-spacing: 0;
  color: var(--text-muted);
  margin-left: 0.35rem;
}

.locale {
  width: auto;
  font-size: 0.7rem;
  color: var(--text-muted);
  border-color: var(--surface-2);
  border-radius: 6px;
  padding: 0.15rem 1.4rem 0.15rem 0.4rem;
  background-position: right 0.35rem center;
}

.app-main {
  flex: 1;
  padding: 1rem;
  max-width: 640px;
  width: 100%;
  margin: 0 auto;
}
</style>
