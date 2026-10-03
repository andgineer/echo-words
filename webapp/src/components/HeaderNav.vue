<script setup>
import { Activity, BarChart3, Plus } from "lucide-vue-next";
import { serverReach, serverUnanswered } from "../composables/useServerReach.js";
import { useI18n } from "../i18n/index.js";

const TABS = [
  { id: "add", labelKey: "nav.words", icon: Plus, color: "var(--nav-words)" },
  { id: "stats", labelKey: "nav.stats", icon: BarChart3, color: "var(--nav-stats)" },
  { id: "status", labelKey: "nav.status", icon: Activity, color: "var(--nav-status)" },
];

const { t } = useI18n();

defineProps({
  view: { type: String, default: "add" },
});
const emit = defineEmits(["update:view"]);

function alerted(tab) {
  return tab.id === "status" && serverUnanswered.value;
}

function label(tab) {
  if (!alerted(tab)) return t(tab.labelKey);
  return `${t(tab.labelKey)} — ${t(`reach.${serverReach.value.failure.kind}`)}`;
}
</script>

<template>
  <nav class="seg-container" role="tablist" :aria-label="t('nav.label')">
    <button
      v-for="tab in TABS"
      :key="tab.id"
      type="button"
      class="seg-btn"
      :class="{ active: view === tab.id }"
      :style="{ '--tab-color': tab.color }"
      role="tab"
      :aria-selected="view === tab.id"
      :aria-label="label(tab)"
      :title="label(tab)"
      :data-testid="`nav-${tab.id}`"
      @click="emit('update:view', tab.id)"
    >
      <component :is="tab.icon" :size="20" aria-hidden="true" />
      <span v-if="alerted(tab)" class="alert-dot" data-testid="status-alert" aria-hidden="true" />
    </button>
  </nav>
</template>

<style scoped>
.seg-container {
  display: flex;
  align-items: center;
  gap: 1px;
  background: var(--field-deep);
  border: 1px solid var(--border);
  border-radius: 11px;
  padding: 3px;
}

.seg-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 36px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s,
    box-shadow 0.15s;
  background: color-mix(in srgb, var(--tab-color) 14%, transparent);
  color: var(--tab-color);
  padding: 0;
}

.seg-btn:active {
  transform: scale(0.95);
}

.seg-btn.active {
  background: var(--tab-color);
  color: #fff;
  box-shadow: 0 4px 12px color-mix(in srgb, var(--tab-color) 40%, transparent);
}

.alert-dot {
  position: absolute;
  top: 4px;
  right: 6px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--error);
  box-shadow: 0 0 0 2px var(--field-deep);
}
</style>
