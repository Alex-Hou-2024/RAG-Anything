import { apiUrl, publicUrl } from "./base-url.js";

/** A normalized error returned to pages for HTTP and network failures. */
export class ApiError extends Error {
  constructor(message, status = 0, details = undefined, code = undefined) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
    this.code = code;
  }
}

async function errorFrom(response) {
  const fallback = `请求失败（${response.status}）`;
  try {
    const payload = await response.json();
    const error = payload?.error;
    return new ApiError(
      error?.message || payload?.detail || fallback,
      response.status,
      error?.details,
      error?.code,
    );
  } catch {
    return new ApiError(fallback, response.status);
  }
}

async function fetchResponse(url, options = {}) {
  try {
    return await fetch(url, options);
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError("无法连接到服务，请检查网络后重试。", 0, undefined, "network_error");
  }
}

async function requestJson(url, options = {}) {
  const headers = new Headers(options.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  const response = await fetchResponse(url, { ...options, headers });
  if (!response.ok) throw await errorFrom(response);
  if (response.status === 204) return null;

  try {
    return await response.json();
  } catch {
    throw new ApiError("服务返回了无效的 JSON 响应。", response.status, undefined, "invalid_response");
  }
}

/** Call an application endpoint below the VITE_API_BASE_URL API namespace. */
export function api(path, options = {}) {
  return requestJson(apiUrl(path), options);
}

/** Call a same-origin public endpoint, such as FastAPI's /healthz route. */
export function publicApi(path, options = {}) {
  return requestJson(publicUrl(path), options);
}

/**
 * Submit a text retrieval query and decode the API's SSE response incrementally.
 * All query routes flow through apiUrl, so a production build does not need a
 * Vite development proxy.
 */
export async function streamQuery(payload, handlers = {}, endpoint = "query") {
  const response = await fetchResponse(apiUrl(endpoint), {
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
      dispatchEvents(events, handlers);
      if (done) break;
    }
    if (pending.trim()) dispatchEvents([pending], handlers);
  } finally {
    reader.releaseLock();
  }
}

function dispatchEvents(eventBlocks, handlers) {
  for (const eventBlock of eventBlocks) {
    const event = parseSseEvent(eventBlock);
    if (event) handlers[event.name]?.(event.data);
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

export async function uploadQueryImage(file) {
  if (!(file instanceof File) || !file.type.startsWith("image/")) {
    throw new TypeError("请选择有效的图片文件");
  }
  const body = new FormData();
  body.append("image", file, file.name);
  return api("query/multimodal/images", { method: "POST", body });
}
