const NAVIGATION = [
  ["/documents", "文档管理"],
  ["/chat", "对话问答"],
  ["/configuration", "配置指南"],
];

export function createLayout(activePath, content, lightragAvailable = false, ragStatus = {}) {
  const shell = document.createElement("div");
  shell.className = "app-shell";

  const header = document.createElement("header");
  header.className = "topbar";
  const brand = document.createElement("a");
  brand.className = "brand";
  brand.href = "/documents";
  brand.dataset.route = "";
  brand.textContent = "文档知识库";
  header.append(brand);

  const nav = document.createElement("nav");
  nav.setAttribute("aria-label", "主导航");
  const navigation = lightragAvailable ? [...NAVIGATION, ["/lightrag", "知识图谱"]] : NAVIGATION;
  for (const [path, label] of navigation) {
    const link = document.createElement("a");
    link.href = path;
    if (path !== "/lightrag") link.dataset.route = "";
    link.textContent = label;
    if (path === activePath) link.setAttribute("aria-current", "page");
    nav.append(link);
  }
  header.append(nav);

  const main = document.createElement("main");
  main.className = "page-content";
  if (ragStatus.code === "missing_model_key") {
    const banner = document.createElement("p");
    banner.className = "model-key-banner";
    banner.setAttribute("role", "alert");
    banner.textContent = "未配置模型密钥，请在项目环境变量中设置 `OPENAI_API_KEY`";
    main.append(banner);
  }
  main.append(content);
  shell.append(header, main);
  return shell;
}

export function createNotice(message, kind = "error") {
  const notice = document.createElement("p");
  notice.className = `notice notice--${kind}`;
  notice.setAttribute("role", kind === "error" ? "alert" : "status");
  notice.textContent = message;
  return notice;
}
