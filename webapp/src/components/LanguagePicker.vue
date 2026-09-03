<script setup>
import { Pencil } from "lucide-vue-next";
import { useI18n } from "../i18n/index.js";

const { t } = useI18n();

defineProps({
  languages: { type: Array, default: () => [] },
  selected: { type: String, default: "" },
});
const emit = defineEmits(["update:selected", "edit"]);
</script>

<template>
  <div v-if="languages.length" class="lang-row">
    <div class="seg-container lang-seg" role="tablist" :aria-label="t('languages.title')">
      <button
        v-for="lang in languages"
        :key="lang.code"
        type="button"
        class="lang-btn"
        :class="{ active: lang.code === selected }"
        role="tab"
        :aria-selected="lang.code === selected"
        :data-testid="`lang-${lang.code}`"
        @click="emit('update:selected', lang.code)"
      >
        {{ lang.name }}
      </button>
    </div>
    <button
      type="button"
      class="icon-btn"
      :title="t('languages.edit')"
      :aria-label="t('languages.edit')"
      data-testid="edit-languages"
      @click="emit('edit')"
    >
      <Pencil :size="18" aria-hidden="true" />
    </button>
  </div>
</template>

<style scoped>
.lang-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.seg-container {
  display: flex;
  align-items: center;
  gap: 3px;
  background: var(--field-deep);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 3px;
}

/* One language is still a row: it names the language, and the pencil beside it
   is the only way into the editor. */
.lang-seg {
  flex: 1;
  min-width: 0;
}

.lang-btn {
  flex: 1;
  min-width: 0;
  height: 34px;
  border: none;
  border-radius: 9px;
  font-family: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition:
    background 0.15s,
    color 0.15s,
    box-shadow 0.15s,
    transform 0.1s;
  touch-action: manipulation;
}

.lang-btn:active {
  transform: scale(0.95);
}

.lang-btn.active {
  background: var(--accent);
  color: #fff;
  box-shadow: 0 4px 12px color-mix(in srgb, var(--accent) 40%, transparent);
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  background: none;
  border: 1px solid var(--surface-2);
  border-radius: 10px;
  color: var(--text-muted);
  cursor: pointer;
  transition:
    color 0.15s,
    border-color 0.15s,
    transform 0.1s;
  touch-action: manipulation;
}

.icon-btn:hover {
  color: var(--text);
  border-color: var(--accent);
}

.icon-btn:active {
  transform: scale(0.95);
}
</style>
