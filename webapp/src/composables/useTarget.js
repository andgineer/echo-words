import { ref } from "vue";
import { cachedRequest, readCache } from "../api/cache.js";

const CATALOG = "/api/languages/catalog";
const TARGET = "/api/target";

function isTarget(data) {
  return !!data && typeof data.name === "string";
}

function savedCatalog() {
  const saved = readCache(CATALOG)?.data;
  return Array.isArray(saved) ? saved : [];
}

function savedTarget() {
  const saved = readCache(TARGET)?.data;
  return isTarget(saved) ? saved : null;
}

// The language directory, and the language the app translates into: its directory code
// where it has one, and the name it was configured with either way.
export const catalog = ref(savedCatalog());
export const target = ref(savedTarget());

export function restoreTarget() {
  catalog.value = savedCatalog();
  target.value = savedTarget();
}

export async function loadTarget() {
  const [rows, named] = await Promise.allSettled([
    cachedRequest(CATALOG),
    cachedRequest(TARGET, { validate: isTarget }),
  ]);
  if (rows.status === "fulfilled") catalog.value = rows.value;
  if (named.status === "fulfilled") target.value = named.value;
}
