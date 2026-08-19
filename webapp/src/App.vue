<script setup>
import { ref } from "vue";
import AddView from "./views/AddView.vue";
import StatsView from "./views/StatsView.vue";
import StatusView from "./views/StatusView.vue";

const view = ref("add");
</script>

<template>
  <header class="app-header">
    <h1>echo-words</h1>
    <nav>
      <button class="btn-inline" @click="view = 'add'">Слова</button>
      <button class="btn-inline" @click="view = 'stats'">Статистика</button>
      <button class="btn-inline" @click="view = 'status'">Состояние</button>
    </nav>
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
  justify-content: space-between;
  align-items: center;
}

nav {
  display: flex;
  gap: 0.35rem;
}

.app-header h1 {
  font-size: 1.1rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.app-main {
  flex: 1;
  padding: 1rem;
  max-width: 640px;
  width: 100%;
  margin: 0 auto;
}
</style>
