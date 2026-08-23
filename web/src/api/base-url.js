/**
 * Base URL for application APIs. Vite substitutes VITE_* variables at build
 * time, allowing deployments to choose an API origin without shipping a
 * development-only proxy or a localhost default.
 */
const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

export const apiBaseUrl = (configuredBaseUrl || "/api").replace(/\/+$/, "") || "/api";

/** Build an API URL from a route that may or may not start with a slash. */
export function apiUrl(path = "") {
  return `${apiBaseUrl}/${String(path).replace(/^\/+/, "")}`;
}

/**
 * Build a same-origin URL for public routes that deliberately live outside the
 * `/api` namespace (currently the FastAPI health check).
 */
export function publicUrl(path = "/") {
  const normalizedPath = `/${String(path).replace(/^\/+/, "")}`;

  if (!/^https?:\/\//i.test(apiBaseUrl)) {
    return normalizedPath;
  }

  return new URL(normalizedPath, apiBaseUrl).toString();
}
