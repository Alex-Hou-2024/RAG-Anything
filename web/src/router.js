import { createLayout } from "./components/layout.js";
import { createChatPage } from "./pages/chat.js";
import { createDocumentsPage } from "./pages/documents.js";

const routes = {
  "/documents": createDocumentsPage,
  "/chat": createChatPage,
};

export function startRouter(root, { lightragAvailable = false, ragAvailable = false } = {}) {
  let dispose = () => {};

  function render() {
    const path = location.pathname === "/" ? "/documents" : location.pathname;
    if (location.pathname === "/") history.replaceState({}, "", path);
    const createPage = routes[path] || routes["/documents"];
    dispose();
    const page = createPage({ ragAvailable });
    root.replaceChildren(createLayout(path in routes ? path : "/documents", page.element, lightragAvailable));
    dispose = page.dispose;
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
