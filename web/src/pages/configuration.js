import { getConfigurationGuide } from "../api/configuration.js";
import { createNotice } from "../components/layout.js";

function statusFor(item) {
  if (!item.valid) return ["配置无效", "failed"];
  if (!item.configured) {
    if (item.key.startsWith("OBJECT_STORAGE_")) return ["未配置（回退本地目录）", "muted"];
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

async function copyVariableName(name, button, noticeHost) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(name);
    } else {
      const input = document.createElement("textarea");
      input.value = name;
      input.setAttribute("readonly", "");
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.append(input);
      input.select();
      if (!document.execCommand("copy")) throw new Error("copy command failed");
      input.remove();
    }
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
    </section>`;

  const tbody = page.querySelector("tbody");
  const noticeHost = page.querySelector(".configuration-notice");
  let disposed = false;

  async function loadGuide() {
    noticeHost.replaceChildren(createNotice("正在加载配置清单…", "info"));
    try {
      const response = await getConfigurationGuide();
      if (disposed) return;
      if (!Array.isArray(response?.items)) throw new Error("配置清单响应格式无效");
      tbody.replaceChildren(...response.items.map((item) => renderGuideRow(item, noticeHost)));
      noticeHost.replaceChildren();
    } catch (error) {
      if (!disposed) noticeHost.replaceChildren(createNotice(`无法加载配置清单：${error.message}`));
    }
  }

  void loadGuide();
  return { element: page, dispose: () => { disposed = true; } };
}
