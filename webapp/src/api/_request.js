export async function apiRequest(path, { method = "GET", body } = {}) {
  const init = { method };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const resp = await fetch(path, init);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    const detail = err.detail;
    const message = Array.isArray(detail)
      ? detail[0]?.msg || `HTTP ${resp.status}`
      : detail || `HTTP ${resp.status}`;
    const e = new Error(message);
    e.status = resp.status;
    throw e;
  }
  if (resp.status === 204 || resp.headers.get("content-length") === "0") return null;
  return resp.json();
}
