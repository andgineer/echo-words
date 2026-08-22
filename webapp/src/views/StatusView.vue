<script setup>
import { onMounted, ref } from "vue";
import { apiRequest } from "../api/_request.js";
import { useI18n } from "../i18n/index.js";

const { t, locale } = useI18n();
const status = ref(null);
const error = ref("");

function formattedTime(value) {
  if (!value) return t("status.never");
  return new Intl.DateTimeFormat(locale.value, {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function paidAvailability(item) {
  return item.paid_available_today
    ? t("status.paidAvailable")
    : t("status.paidUnavailable", { reason: item.paid_refusal });
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
    <h2>{{ t("status.title") }}</h2>
    <p v-if="status.pool.available">
      {{
        t("status.pool", {
          usable: status.pool.providers_usable,
          total: status.pool.providers_total,
        })
      }}
      <strong v-if="status.pool.degraded">{{ t("status.degraded") }}</strong>
    </p>
    <p v-else class="error">{{ t("status.poolUnavailable", { error: status.pool.error }) }}</p>
    <div v-if="status.pool.missing_keys?.length" class="diagnostics">
      <p><b>{{ t("status.missingFreeKeys") }}</b></p>
      <p v-for="key in status.pool.missing_keys" :key="key.api_key_ref">
        {{ key.api_key_ref }}<span v-if="key.help"> — {{ key.help }}</span>
      </p>
    </div>
    <div v-if="status.pool.direct_missing_keys?.length" class="diagnostics">
      <p><b>{{ t("status.missingPaidKeys") }}</b></p>
      <p v-for="key in status.pool.direct_missing_keys" :key="key.api_key_ref">
        {{ key.api_key_ref }}<span v-if="key.help"> — {{ key.help }}</span>
      </p>
    </div>
    <p>
      {{
        t("status.paidCalls", {
          today: status.paid_calls.today,
          cap: status.paid_calls.daily_cap || "∞",
        })
      }}
    </p>
    <p>
      {{ t("status.ankiweb", { result: status.anki.last_result || t("status.neverSynced") }) }}
      <span v-if="status.anki.unsynced_changes">{{ t("status.unsynced") }}</span>
    </p>
    <p>{{ t("status.lastSync", { time: formattedTime(status.anki.last_sync_at) }) }}</p>
    <p v-if="status.anki.error" class="error">
      {{ t("status.syncError", { error: status.anki.error }) }}
    </p>
    <p v-if="status.anki.full_sync_required" class="error">
      {{ t("status.fullSyncRequired") }}
    </p>
    <article v-for="(item, code) in status.languages" :key="code" class="language">
      <p><b>{{ item.name }}</b> — {{ item.deck }}</p>
      <p>
        {{
          t("status.paidModel", {
            alias: item.paid_alias || t("status.paidNotConfigured"),
            availability: paidAvailability(item),
          })
        }}
      </p>
      <p v-if="item.last_call">
        {{
          t("status.lastCall", {
            result: item.last_call.ok ? t("status.callOk") : t("status.callFailed"),
            model: item.last_call.model || t("status.unknownModel"),
            time: formattedTime(item.last_call.at),
          })
        }}
        <span v-if="item.last_call.error" class="error"> · {{ item.last_call.error }}</span>
      </p>
      <p v-else>{{ t("status.noCalls") }}</p>
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
