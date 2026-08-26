<script setup>
import { onMounted, ref } from "vue";
import { apiRequest } from "../api/_request.js";
import { useI18n } from "../i18n/index.js";

const { t } = useI18n();
const stats = ref(null);
const error = ref("");

onMounted(async () => {
  try {
    stats.value = await apiRequest("/api/stats");
  } catch (e) {
    error.value = e.message;
  }
});
</script>

<template>
  <p v-if="error" class="error">{{ error }}</p>
  <section v-if="stats" class="card">
    <h2>{{ t("stats.title") }}</h2>
    <article v-for="(item, code) in stats.languages" :key="code" class="row">
      <h3>{{ item.name }}</h3>
      <p>{{ t("stats.today", { count: item.today }) }}</p>
      <p>{{ t("stats.last7Days", { count: item.last_7_days }) }}</p>
      <p>{{ t("stats.allTime", { count: item.all_time }) }}</p>
      <p class="muted">
        {{ t("stats.sinceStart", { lookupOnly: item.lookup_only }) }}
      </p>
    </article>
  </section>
</template>

<style scoped>
h2,
h3 {
  margin-bottom: 0.5rem;
}

.row + .row {
  border-top: 1px solid var(--border);
  margin-top: 1rem;
  padding-top: 1rem;
}

.muted {
  color: var(--text-muted);
  font-size: 0.8rem;
}

.error {
  color: var(--error);
}
</style>
