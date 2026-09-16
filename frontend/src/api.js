// Every call goes to our own FastAPI backend — the model key never reaches the browser.

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        // FastAPI validation errors arrive as a list.
        detail = body.detail[0].msg.replace(/^Value error, /, "");
      }
    } catch {
      // Non-JSON error body — keep the status-code message.
    }
    throw new ApiError(detail, res.status);
  }
  return res.json();
}

export const api = {
  meta: () => request("/meta"),
  login: (password) =>
    request("/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => request("/logout", { method: "POST" }),

  generate: (payload) =>
    request("/generate", { method: "POST", body: JSON.stringify(payload) }),

  builds: ({ q = "", civ = "", primaryFocus = "" } = {}) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (civ) params.set("civ", civ);
    if (primaryFocus) params.set("primary_focus", primaryFocus);
    const query = params.toString();
    return request(`/builds${query ? `?${query}` : ""}`);
  },
  build: (id) => request(`/builds/${id}`),
  rename: (id, title) =>
    request(`/builds/${id}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  remove: (id) => request(`/builds/${id}`, { method: "DELETE" }),

  usage: () => request("/usage"),

  compare: (buildIds) =>
    request("/compare", { method: "POST", body: JSON.stringify({ build_ids: buildIds }) }),
};

export { ApiError };
