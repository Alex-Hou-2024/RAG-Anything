import { api } from "./client.js";

/** Fetch the server-owned, non-secret runtime configuration catalogue. */
export function getConfigurationGuide() {
  return api("config/guide");
}
