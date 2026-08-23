import { startRouter } from "./router.js";

const root = document.querySelector("#app");
if (!root) throw new Error("找不到应用根节点");
startRouter(root);
