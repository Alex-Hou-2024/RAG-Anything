import { createNotice } from "../components/layout.js";

const MODEL_BASE_URL = "https://api.openai.com/v1";

const CONFIGURATION_ITEMS = [
  {
    name: "OPENAI_API_KEY",
    required: "必填",
    secret: true,
    options: "OpenAI 或兼容服务的 API Key",
    recommended: "—",
    purpose: "供 chat、vision、embedding 三类模型调用使用；密钥不会在此页面显示。",
    consequence: "RAG 服务不会初始化，无法上传文档或提问。",
  },
  {
    name: "LLM_MODEL",
    required: "可选",
    options: "任意 OpenAI 兼容聊天模型",
    recommended: "gpt-4o-mini",
    purpose: "用于检索后的回答生成。",
    consequence: "使用默认聊天模型；若服务不支持该模型，问答会失败。",
  },
  {
    name: "LLM_BASE_URL",
    required: "可选",
    options: "完整 http(s) OpenAI 兼容地址",
    recommended: MODEL_BASE_URL,
    purpose: "聊天模型服务地址，可改为任意 OpenAI 兼容服务。",
    consequence: "使用默认 OpenAI 服务地址。",
  },
  {
    name: "VISION_MODEL",
    required: "可选",
    options: "支持图片输入的 OpenAI 兼容模型",
    recommended: "gpt-4o-mini",
    purpose: "为文档图片生成描述，供多模态入库和问答使用。",
    consequence: "使用默认视觉模型；图片描述能力可能不可用。",
  },
  {
    name: "VISION_BASE_URL",
    required: "可选",
    options: "完整 http(s) OpenAI 兼容地址",
    recommended: MODEL_BASE_URL,
    purpose: "视觉模型服务地址。",
    consequence: "使用默认 OpenAI 服务地址。",
  },
  {
    name: "EMBEDDING_MODEL",
    required: "可选",
    options: "OpenAI 兼容 embedding 模型",
    recommended: "text-embedding-3-small",
    purpose: "把文档和问题转换为向量，供召回使用。",
    consequence: "使用默认 embedding 模型。",
  },
  {
    name: "EMBEDDING_BASE_URL",
    required: "可选",
    options: "完整 http(s) OpenAI 兼容地址",
    recommended: MODEL_BASE_URL,
    purpose: "embedding 模型服务地址。",
    consequence: "使用默认 OpenAI 服务地址。",
  },
  {
    name: "EMBEDDING_DIMENSION",
    required: "可选",
    options: "正整数；必须匹配模型维度",
    recommended: "1536",
    purpose: "向量存储维度。text-embedding-3-small 对应 1536，text-embedding-3-large 对应 3072。",
    consequence: "维度不匹配是最常见的静默故障，会导致索引或检索异常。",
  },
  {
    name: "RAG_PARSER",
    required: "可选",
    options: "auto / mineru / python / docling / paddleocr",
    recommended: "auto",
    purpose: "auto 优先 MinerU 并回退 Python；MinerU 适合 OCR、版面和表格；python 是轻量文本/图片回退；Docling 与 PaddleOCR 需额外安装。",
    consequence: "使用 auto；缺少增强解析器时会降级，OCR、版面还原和表格结构识别受限。",
  },
  {
    name: "RAG_WORKING_DIR",
    required: "必填",
    options: "可写的持久化目录",
    recommended: "/data/rag_storage",
    purpose: "保存 LightRAG 索引、向量与知识图谱。",
    consequence: "若不是持久卷，服务重启后索引会丢失。",
  },
  {
    name: "RAG_OUTPUT_DIR",
    required: "必填",
    options: "可写的持久化目录",
    recommended: "/data/output",
    purpose: "保存文档解析输出和中间结果。",
    consequence: "若不是持久卷，解析结果会在重启后丢失。",
  },
  {
    name: "RAG_PARSER_CACHE_DIR",
    required: "必填",
    options: "可写的持久化目录",
    recommended: "/data/rag_parser_cache",
    purpose: "保存解析器和模型缓存，避免重复下载。",
    consequence: "非持久目录会导致重启后重新下载或解析失败。",
  },
  {
    name: "DATABASE_URL",
    required: "必填",
    secret: true,
    options: "Postgres 连接 URL（本地部署可使用持久化 SQLite）",
    recommended: "由部署环境提供",
    purpose: "持久化文档元数据、处理状态和失败原因。",
    consequence: "服务无法启动或重启后无法保留文档列表与状态。",
  },
  {
    name: "OBJECT_STORAGE_ENDPOINT",
    required: "可选（S3 组）",
    options: "S3 兼容 endpoint",
    recommended: "—",
    purpose: "启用 S3 兼容对象存储。endpoint、bucket、access key、secret 必须作为一组配置。",
    consequence: "整组不填时回退本地目录；只填部分会被启动校验拒绝。",
  },
  {
    name: "OBJECT_STORAGE_BUCKET",
    required: "可选（S3 组）",
    options: "已创建的 bucket 名称",
    recommended: "—",
    purpose: "S3 文档源文件的 bucket；必须与 S3 组其余变量一同配置。",
    consequence: "整组不填时回退本地目录；只填部分会被启动校验拒绝。",
  },
  {
    name: "OBJECT_STORAGE_ACCESS_KEY_ID",
    required: "可选（S3 组）",
    secret: true,
    options: "S3 access key",
    recommended: "—",
    purpose: "访问 S3 兼容对象存储的凭据；仅显示是否配置。",
    consequence: "整组不填时回退本地目录；只填部分会被启动校验拒绝。",
  },
  {
    name: "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    required: "可选（S3 组）",
    secret: true,
    options: "S3 secret key",
    recommended: "—",
    purpose: "访问 S3 兼容对象存储的密钥；仅显示是否配置。",
    consequence: "整组不填时回退本地目录；只填部分会被启动校验拒绝。",
  },
];

function statusFor(item, ragStatus) {
  if (item.name === "OPENAI_API_KEY") {
    return ragStatus.code === "missing_model_key" ? ["未配置", "failed"] : ["已配置", "ready"];
  }
  if (item.name === "DATABASE_URL") return ["已配置", "ready"];
  if (item.name.startsWith("OBJECT_STORAGE_")) return ["未配置（回退本地目录）", "muted"];
  return ["使用默认值", "muted"];
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

export function createConfigurationPage({ ragStatus = {} } = {}) {
  const page = document.createElement("section");
  page.className = "page page--configuration";
  page.innerHTML = `
    <div class="page-heading">
      <div><p class="eyebrow">部署准备</p><h1>配置指南</h1><p>在项目环境变量中配置以下项目。密钥类变量只显示状态，绝不会回显实际值。</p></div>
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
  for (const item of CONFIGURATION_ITEMS) {
    const row = document.createElement("tr");
    const [status, tone] = statusFor(item, ragStatus);
    const variable = document.createElement("td");
    variable.className = "configuration-variable";
    const code = document.createElement("code");
    code.textContent = item.name;
    const copy = document.createElement("button");
    copy.className = "button button--secondary button--copy";
    copy.type = "button";
    copy.textContent = "复制";
    copy.setAttribute("aria-label", `复制 ${item.name}`);
    copy.addEventListener("click", () => copyVariableName(item.name, copy, noticeHost));
    variable.append(code, copy);
    const required = document.createElement("td");
    required.textContent = item.required;
    const current = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `badge badge--${tone}`;
    badge.textContent = status;
    current.append(badge);
    const options = document.createElement("td");
    options.textContent = item.options;
    const recommended = document.createElement("td");
    recommended.textContent = item.recommended;
    const purpose = document.createElement("td");
    purpose.textContent = item.purpose;
    const consequence = document.createElement("td");
    consequence.textContent = item.consequence;
    row.append(variable, required, current, options, recommended, purpose, consequence);
    tbody.append(row);
  }

  return { element: page, dispose: () => {} };
}
