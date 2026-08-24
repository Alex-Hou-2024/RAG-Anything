import { publicApi } from "./api/client.js";
import { createLayout } from "./components/layout.js";
import { createChatPage } from "./pages/chat.js";
import { createConfigurationPage } from "./pages/configuration.js";
import { createDocumentsPage } from "./pages/documents.js";

const routes = {
  "/documents": createDocumentsPage,
  "/chat": createChatPage,
  "/configuration": createConfigurationPage,
};

export function startRouter(root, initialState = {}) {
  let lightragAvailable = Boolean(initialState.lightragAvailable);
  let ragAvailable = Boolean(initialState.ragAvailable);
  let ragStatus = initialState.ragStatus || {};
  let dispose = () => {};

  function render() {
    const path = location.pathname === "/" ? "/documents" : location.pathname;
    if (location.pathname === "/") history.replaceState({}, "", path);
    const createPage = routes[path] || routes["/documents"];
    dispose();
    const page = createPage({ ragAvailable, ragStatus });
    root.replaceChildren(createLayout(path in routes ? path : "/documents", page.element, lightragAvailable, ragStatus, redetectRuntime));
    dispose = page.dispose;
  }

  async function redetectRuntime() {
    const health = await publicApi("healthz");
    lightragAvailable = Boolean(health.lightrag_webui);
    ragAvailable = Boolean(health.rag?.initialized);
    ragStatus = health.rag || { initialized: false, code: null };
    render();
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-route]");
    if (!link || event.defaultPrevented || event.metaKey || event.ctrlKey) return;
    event.preventDefault();
    if (link.pathname !== location.pathname) {
      history.pushState({}, "", link.pathname);
      render();
    }
  });
  window.addEventListener("popstate", render);
  render();
}
