<script setup>
import { onMounted, ref } from "vue";
import { apiRequest } from "../api/_request.js";

const status = ref(null);
const error = ref("");

function formattedTime(value) {
  if (!value) return "нет";
  return new Intl.DateTimeFormat("ru", { dateStyle: "short", timeStyle: "short" }).format(
    new Date(value),
  );
}

onMounted(async () => {
  try {
    status.value = await apiRequest("/api/status");
  } catch (e) {
    error.value = e.message;
  }
});
</script>

<template>
  <p v-if="error" class="error">{{ error }}</p>
  <section v-if="status" class="card">
    <h2>Состояние</h2>
    <p v-if="status.pool.available">
      LLM: {{ status.pool.providers_usable }}/{{ status.pool.providers_total }} провайдеров
      <strong v-if="status.pool.degraded"> · ограниченный резерв</strong>
    </p>
    <p v-else class="error">LLM недоступен: {{ status.pool.error }}</p>
    <div v-if="status.pool.missing_keys?.length" class="diagnostics">
      <p><b>Нет ключей бесплатного пула:</b></p>
      <p v-for="key in status.pool.missing_keys" :key="key.api_key_ref">
        {{ key.api_key_ref }}<span v-if="key.help"> — {{ key.help }}</span>
      </p>
    </div>
    <div v-if="status.pool.direct_missing_keys?.length" class="diagnostics">
      <p><b>Нет ключей платной модели:</b></p>
      <p v-for="key in status.pool.direct_missing_keys" :key="key.api_key_ref">
        {{ key.api_key_ref }}<span v-if="key.help"> — {{ key.help }}</span>
      </p>
    </div>
    <p>Платных вызовов сегодня: {{ status.paid_calls.today }}/{{ status.paid_calls.daily_cap || "∞" }}</p>
    <p>
      AnkiWeb: {{ status.anki.last_result || "ещё не синхронизировался" }}
      <span v-if="status.anki.unsynced_changes"> · есть несинхронизированные изменения</span>
    </p>
    <p>Последняя синхронизация: {{ formattedTime(status.anki.last_sync_at) }}</p>
    <p v-if="status.anki.error" class="error">Ошибка синхронизации: {{ status.anki.error }}</p>
    <p v-if="status.anki.full_sync_required" class="error">
      Нужна ручная односторонняя синхронизация Anki.
    </p>
    <article v-for="(item, code) in status.languages" :key="code" class="language">
      <p><b>{{ item.name }}</b> — {{ item.deck }}</p>
      <p>
        Платная модель: {{ item.paid_alias || "не настроена" }} ·
        {{ item.paid_available_today ? "доступна" : `недоступна: ${item.paid_refusal}` }}
      </p>
      <p v-if="item.last_call">
        Последний вызов: {{ item.last_call.ok ? "успешно" : "ошибка" }} ·
        {{ item.last_call.model || "модель неизвестна" }} · {{ formattedTime(item.last_call.at) }}
        <span v-if="item.last_call.error" class="error"> · {{ item.last_call.error }}</span>
      </p>
      <p v-else>Последних вызовов нет.</p>
    </article>
  </section>
</template>

<style scoped>
h2 {
  margin-bottom: 0.75rem;
}

p + p,
.language {
  margin-top: 0.5rem;
}

.diagnostics,
.language {
  margin-top: 0.75rem;
}

.error {
  color: var(--error);
}

strong {
  color: var(--warning);
}
</style>
