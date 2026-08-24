import { getConfigurationGuide } from "../api/configuration.js";
import { createNotice } from "../components/layout.js";

const TEMPLATE_PLACEHOLDERS = {
  OPENAI_API_KEY: "<在此填入你的密钥>",
  DATABASE_URL: "<在此填入数据库连接地址>",
  OBJECT_STORAGE_ACCESS_KEY_ID: "<在此填入 S3 access key>",
  OBJECT_STORAGE_SECRET_ACCESS_KEY: "<在此填入 S3 secret key>",
};
const S3_KEYS = new Set([
  "OBJECT_STORAGE_ENDPOINT",
  "OBJECT_STORAGE_BUCKET",
  "OBJECT_STORAGE_ACCESS_KEY_ID",
  "OBJECT_STORAGE_SECRET_ACCESS_KEY",
]);

function statusFor(item) {
  if (!item.valid) return ["配置无效", "failed"];
  if (!item.configured) {
    if (S3_KEYS.has(item.key)) return ["未配置（回退本地目录）", "muted"];
    return ["未配置", item.required ? "failed" : "muted"];
  }
  if (item.uses_default) return ["使用默认值", "muted"];
  return ["已配置", "ready"];
}

function renderGuideRow(item, noticeHost) {
  const row = document.createElement("tr");
  const [status, tone] = statusFor(item);
  const variable = document.createElement("td");
  variable.className = "configuration-variable";
  const code = document.createElement("code");
  code.textContent = item.key;
  const copy = document.createElement("button");
  copy.className = "button button--secondary button--copy";
  copy.type = "button";
  copy.textContent = "复制";
  copy.setAttribute("aria-label", `复制 ${item.key}`);
  copy.addEventListener("click", () => copyVariableName(item.key, copy, noticeHost));
  variable.append(code, copy);

  const required = document.createElement("td");
  required.textContent = item.required ? "必填" : "可选";
  const current = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = `badge badge--${tone}`;
  badge.textContent = status;
  current.append(badge);
  const options = document.createElement("td");
  options.textContent = (item.options || []).join(" / ") || "—";
  const recommended = document.createElement("td");
  recommended.textContent = item.recommended === null || item.recommended === undefined
    ? "—"
    : String(item.recommended);
  const description = document.createElement("td");
  description.textContent = item.description || "—";
  const impact = document.createElement("td");
  impact.textContent = item.impact || "—";
  row.append(variable, required, current, options, recommended, description, impact);
  return row;
}

function effectiveTemplateValue(item) {
  if (Object.hasOwn(TEMPLATE_PLACEHOLDERS, item.key)) return TEMPLATE_PLACEHOLDERS[item.key];
  if (item.effective_value !== null && item.effective_value !== undefined) {
    return String(item.effective_value);
  }
  if (item.recommended !== null && item.recommended !== undefined) return String(item.recommended);
  return "";
}

/** Build a safe, paste-ready .env snippet from the server-owned guide items. */
export function buildConfigurationTemplate(items) {
  const lines = [
    "# RAG-Anything 配置模板",
    "# 将内容粘贴到 Project Config → Environment；保存后需要重新部署才会生效。",
    "",
  ];
  const regularItems = items.filter((item) => !S3_KEYS.has(item.key));
  for (const item of regularItems) {
    lines.push(`${item.key}=${effectiveTemplateValue(item)}`);
  }

  const s3Items = items.filter((item) => S3_KEYS.has(item.key));
  if (s3Items.some((item) => item.configured)) {
    lines.push("", "# 已启用 S3 兼容存储：四项必须同时填写。 ");
    for (const item of s3Items) lines.push(`${item.key}=${effectiveTemplateValue(item)}`);
  } else {
    lines.push(
      "",
      "# 可选 S3 兼容存储：保持以下四项不填即可使用本地目录；如启用则四项必须同时填写。",
      "# OBJECT_STORAGE_ENDPOINT=",
      "# OBJECT_STORAGE_BUCKET=",
      "# OBJECT_STORAGE_ACCESS_KEY_ID=<在此填入 S3 access key>",
      "# OBJECT_STORAGE_SECRET_ACCESS_KEY=<在此填入 S3 secret key>",
    );
  }
  return lines.join("\n");
}

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

async function copyVariableName(name, button, noticeHost) {
  try {
    await copyText(name);
    button.textContent = "已复制";
    noticeHost.replaceChildren(createNotice(`${name} 已复制到剪贴板。`, "success"));
  } catch {
    noticeHost.replaceChildren(createNotice(`无法自动复制 ${name}，请手动选择变量名。`));
  }
  window.setTimeout(() => { button.textContent = "复制"; }, 1800);
}

export function createConfigurationPage() {
  const page = document.createElement("section");
  page.className = "page page--configuration";
  page.innerHTML = `
    <div class="page-heading">
      <div><p class="eyebrow">部署准备</p><h1>配置指南</h1><p>配置状态和说明由当前服务实时提供。密钥类变量只显示状态，绝不会回显实际值。</p></div>
    </div>
    <section class="configuration-panel" aria-labelledby="configuration-title">
      <div class="section-title"><div><h2 id="configuration-title">运行配置清单</h2><p class="muted">带“必填”的项目需要在部署前确认；修改后请重启服务。</p></div></div>
      <div class="configuration-notice" aria-live="polite"></div>
      <div class="configuration-table-wrap"><table class="configuration-table">
        <thead><tr><th scope="col">变量名</th><th scope="col">是否必填</th><th scope="col">当前状态</th><th scope="col">可选值</th><th scope="col">推荐值</th><th scope="col">作用说明</th><th scope="col">不配置的后果</th></tr></thead>
        <tbody></tbody>
      </table></div>
    </section>
    <section class="configuration-panel configuration-template-panel" aria-labelledby="template-title">
      <div class="section-title"><div><h2 id="template-title">配置模板</h2><p class="muted">模板使用当前安全的生效值和推荐默认值；所有密钥位置均为占位符。</p></div><button class="button button--primary configuration-template-copy" type="button" disabled>复制完整配置模板</button></div>
      <pre class="configuration-template" aria-label="配置模板预览"></pre>
      <p class="configuration-template-help">复制后请粘贴到 <strong>Project Config → Environment</strong>。保存配置后，必须重新部署服务才会生效。</p>
    </section>`;

  const tbody = page.querySelector("tbody");
  const noticeHost = page.querySelector(".configuration-notice");
  const templatePreview = page.querySelector(".configuration-template");
  const templateCopyButton = page.querySelector(".configuration-template-copy");
  let template = "";
  let disposed = false;

  templateCopyButton.addEventListener("click", async () => {
    try {
      await copyText(template);
      templateCopyButton.textContent = "模板已复制";
      noticeHost.replaceChildren(createNotice("完整配置模板已复制。保存到 Project Config → Environment 后请重新部署。", "success"));
    } catch {
      noticeHost.replaceChildren(createNotice("无法自动复制配置模板，请手动选择并复制预览内容。"));
    }
    window.setTimeout(() => { templateCopyButton.textContent = "复制完整配置模板"; }, 1800);
  });

  async function loadGuide() {
    noticeHost.replaceChildren(createNotice("正在加载配置清单…", "info"));
    try {
      const response = await getConfigurationGuide();
      if (disposed) return;
      if (!Array.isArray(response?.items)) throw new Error("配置清单响应格式无效");
      tbody.replaceChildren(...response.items.map((item) => renderGuideRow(item, noticeHost)));
      template = buildConfigurationTemplate(response.items);
      templatePreview.textContent = template;
      templateCopyButton.disabled = false;
      noticeHost.replaceChildren();
    } catch (error) {
      if (!disposed) noticeHost.replaceChildren(createNotice(`无法加载配置清单：${error.message}`));
    }
  }

  void loadGuide();
  return { element: page, dispose: () => { disposed = true; } };
}
