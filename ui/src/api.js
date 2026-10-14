async function request(method, path, body) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    throw new Error(
      typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : res.statusText,
    );
  }
  return data;
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body = {}) => request("POST", path, body),
  put: (path, body) => request("PUT", path, body),
  patch: (path, body) => request("PATCH", path, body),
  del: (path) => request("DELETE", path),
};

export async function uploadTemplates(file, onlyTcp) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/api/templates/import?only_tcp=${onlyTcp}`, { method: "POST", body: form });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail || res.statusText);
  return data;
}

export function downloadTemplates(ids) {
  window.location.href = `/api/templates/export?ids=${ids.join(",")}`;
}
