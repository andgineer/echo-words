<script setup>
import AddView from "./views/AddView.vue";
</script>

<template>
  <header class="app-header">
    <h1>echo-words</h1>
  </header>
  <main class="app-main">
    <AddView />
  </main>
</template>

<style scoped>
.app-header {
  background: var(--surface);
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
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
