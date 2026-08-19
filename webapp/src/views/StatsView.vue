<script setup>
import { onMounted, ref } from "vue";
import { apiRequest } from "../api/_request.js";

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
    <h2>Статистика</h2>
    <article v-for="(item, code) in stats.languages" :key="code" class="row">
      <h3>{{ item.name }}</h3>
      <p>Сегодня: {{ item.today }}</p>
      <p>За 7 дней: {{ item.last_7_days }}</p>
      <p>Всего: {{ item.all_time }}</p>
      <p class="muted">
        После запуска: дублей {{ item.duplicates }}, без карточки {{ item.lookup_only }}
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
