import { startRouter } from "./router.js";

const root = document.querySelector("#app");
if (!root) throw new Error("找不到应用根节点");

async function start() {
  let lightragAvailable = false;
  try {
    const response = await fetch("/healthz", { headers: { Accept: "application/json" } });
    if (response.ok) lightragAvailable = Boolean((await response.json()).lightrag_webui);
  } catch {
    // The core UI remains usable when the optional capability probe is unavailable.
  }
  startRouter(root, { lightragAvailable });
}

start();
