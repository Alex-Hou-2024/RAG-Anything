/** Same-origin API utilities shared by each application page. */
export class ApiError extends Error {
  constructor(message, status, details = undefined) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

async function errorFrom(response) {
  const fallback = `请求失败（${response.status}）`;
  try {
    const payload = await response.json();
    const error = payload?.error;
    return new ApiError(error?.message || fallback, response.status, error?.details);
  } catch {
    return new ApiError(fallback, response.status);
  }
}

export async function api(path, options = {}) {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) throw await errorFrom(response);
  return response.status === 204 ? null : response.json();
}

export async function streamQuery(payload, handlers) {
  const response = await fetch("/query", {
    method: "POST",
    headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, stream: true }),
  });
  if (!response.ok) throw await errorFrom(response);
  if (!response.body) throw new ApiError("浏览器不支持流式响应", response.status);

  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let pending = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      pending += decoder.decode(value || new Uint8Array(), { stream: !done });
      const events = pending.split(/\r?\n\r?\n/);
      pending = events.pop() || "";
      for (const eventBlock of events) {
        const event = parseSseEvent(eventBlock);
        if (event) handlers[event.name]?.(event.data);
      }
      if (done) break;
    }
    if (pending.trim()) {
      const event = parseSseEvent(pending);
      if (event) handlers[event.name]?.(event.data);
    }
  } finally {
    reader.releaseLock();
  }
}

function parseSseEvent(block) {
  const lines = block.split(/\r?\n/);
  const name = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
  const rawData = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .join("\n");
  if (!name || !rawData) return null;
  try {
    return { name, data: JSON.parse(rawData) };
  } catch {
    return null;
  }
}
