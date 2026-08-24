const NAVIGATION = [
  ["/documents", "文档管理"],
  ["/chat", "对话问答"],
  ["/configuration", "配置指南"],
];

const CONFIGURATION_BY_STATUS = {
  missing_model_key: {
    title: "缺少模型密钥",
    keys: ["OPENAI_API_KEY"],
    detail: "RAG 服务需要一个同时具备 chat、vision、embedding 权限的模型密钥。",
  },
  invalid_model_configuration: {
    title: "模型配置尚未通过校验",
    keys: ["LLM_MODEL", "LLM_BASE_URL", "VISION_MODEL", "VISION_BASE_URL", "EMBEDDING_MODEL", "EMBEDDING_BASE_URL", "EMBEDDING_DIMENSION"],
    detail: "请成套检查 chat、vision、embedding 的模型、服务地址和向量维度。",
  },
  invalid_storage_configuration: {
    title: "持久化存储配置尚未通过校验",
    keys: ["RAG_WORKING_DIR", "RAG_OUTPUT_DIR", "RAG_PARSER_CACHE_DIR"],
    detail: "请确认目录位于可写持久卷；启用 S3 时 endpoint、bucket、access key、secret 必须全部填写。",
  },
};

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const input = document.createElement("textarea");
  input.value = text;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.append(input);
  input.select();
  const copied = document.execCommand("copy");
  input.remove();
  if (!copied) throw new Error("copy command failed");
}

function createReadinessGuide(ragStatus, onRedetect) {
  if (ragStatus?.initialized) return null;
  const guidance = CONFIGURATION_BY_STATUS[ragStatus?.code] || (
    ragStatus?.code
      ? {
        title: "RAG 服务尚未就绪",
        keys: ["OPENAI_API_KEY"],
        detail: "请先检查模型密钥、模型配置和持久化目录。",
      }
      : {
        title: "尚未获取服务状态",
        keys: [],
        detail: "无法确认当前配置状态；请重新检测，或检查服务是否可访问。",
      }
  );
  const card = document.createElement("section");
  card.className = "readiness-guide";
  card.setAttribute("role", "alert");
  const heading = document.createElement("h2");
  heading.textContent = guidance.title;
  const description = document.createElement("p");
  description.textContent = ragStatus?.error || guidance.detail;
  const steps = document.createElement("p");
  steps.className = "readiness-guide__steps";
  steps.textContent = guidance.detail;
  const keyList = document.createElement("div");
  keyList.className = "readiness-guide__keys";
  if (guidance.keys.length) {
    const label = document.createElement("strong");
    label.textContent = "需要检查的变量：";
    keyList.append(label);
  }
  for (const key of guidance.keys) {
    const row = document.createElement("span");
    row.className = "readiness-guide__key";
    const code = document.createElement("code");
    code.textContent = key;
    const copy = document.createElement("button");
    copy.className = "button button--secondary button--copy";
    copy.type = "button";
    copy.textContent = "复制";
    copy.setAttribute("aria-label", `复制 ${key}`);
    copy.addEventListener("click", async () => {
      try {
        await copyText(key);
        copy.textContent = "已复制";
      } catch {
        copy.textContent = "请手动复制";
      }
      window.setTimeout(() => { copy.textContent = "复制"; }, 1800);
    });
    row.append(code, copy);
    keyList.append(row);
  }
  const actions = document.createElement("div");
  actions.className = "readiness-guide__actions";
  const guide = document.createElement("a");
  guide.className = "button button--primary";
  guide.href = "/configuration";
  guide.dataset.route = "";
  guide.textContent = "前往配置指南";
  const redetect = document.createElement("button");
  redetect.className = "button button--secondary";
  redetect.type = "button";
  redetect.textContent = "重新检测";
  const feedback = document.createElement("p");
  feedback.className = "readiness-guide__feedback";
  feedback.setAttribute("aria-live", "polite");
  redetect.addEventListener("click", async () => {
    if (typeof onRedetect !== "function") return;
    redetect.disabled = true;
    feedback.textContent = "正在重新拉取健康状态并刷新运行能力…";
    try {
      await onRedetect();
    } catch (error) {
      feedback.textContent = `重新检测失败：${error.message || "请检查网络后重试。"}`;
      redetect.disabled = false;
    }
  });
  actions.append(guide, redetect);
  card.append(heading, description, steps);
  if (guidance.keys.length) card.append(keyList);
  card.append(actions, feedback);
  return card;
}

export function createLayout(
  activePath,
  content,
  lightragAvailable = false,
  ragStatus = {},
  onRedetect,
) {
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
  const readinessGuide = createReadinessGuide(ragStatus, onRedetect);
  if (readinessGuide) main.append(readinessGuide);
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
