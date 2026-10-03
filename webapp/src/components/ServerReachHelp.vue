<script setup>
import { computed } from "vue";
import { serverReach } from "../composables/useServerReach.js";
import { useI18n } from "../i18n/index.js";

const props = defineProps({
  kind: { type: String, required: true },
});

const { t, locale } = useI18n();

// What failed decides which check comes first; none of them is ruled out by it.
const TAILNET_CHECKS = {
  offline: ["internet"],
  unreachable: ["tailscale", "internet", "vm"],
  "no-answer": ["vm", "internet"],
  "app-down": ["app"],
};

const host = globalThis.location?.hostname || "";
const onTailnet = host.endsWith(".ts.net");
// Tailscale names the machine after the first label and suffixes a taken name, so the
// address is the only reliable source of what to look for in its list.
const machine = host.split(".")[0];

const checks = computed(() => {
  if (onTailnet) return TAILNET_CHECKS[props.kind];
  return props.kind === "offline" ? ["internet"] : ["local"];
});

const answered = computed(() => {
  const at = serverReach.value.answeredAt;
  if (!at) return t("reach.neverAnswered");
  const time = new Intl.DateTimeFormat(locale.value, {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(at));
  return t("reach.lastAnswered", { time });
});
</script>

<template>
  <section class="card" data-testid="server-reach">
    <h2>{{ t(`reach.${kind}`) }}</h2>
    <p class="answered">{{ answered }}</p>
    <p>{{ t("reach.checksTitle") }}</p>
    <ol>
      <li v-for="check in checks" :key="check" :data-testid="`check-${check}`">
        {{ t(`reach.check.${check}`, { machine, host }) }}
      </li>
    </ol>
  </section>
</template>

<style scoped>
h2 {
  margin-bottom: 0.75rem;
}

.answered {
  color: var(--text-muted);
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}

ol {
  margin-top: 0.5rem;
  padding-left: 1.25rem;
  line-height: 1.5;
}

li + li {
  margin-top: 0.5rem;
}
</style>
