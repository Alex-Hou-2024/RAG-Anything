import {
  deleteDocument,
  documentStatus,
  getCapabilities,
  listDocuments,
  uploadDocument,
} from "../api/documents.js";
import { createNotice } from "../components/layout.js";

const ACTIVE_STATUSES = new Set(["pending", "parsing", "indexing"]);
const STATUS_LABELS = {
  pending: "等待处理",
  parsing: "正在解析",
  indexing: "正在索引",
  ready: "已就绪",
  failed: "处理失败",
};

export function createDocumentsPage({ ragAvailable = false, ragStatus = {} } = {}) {
  const page = document.createElement("section");
  page.className = "page page--documents";
  page.innerHTML = `
    <div class="page-heading">
      <div><p class="eyebrow">资料中心</p><h1>文档管理</h1><p>上传多模态文档，跟踪解析进度，并在完成后开始问答。</p></div>
    </div>
    <section class="capability-card" aria-labelledby="capability-title">
      <h2 id="capability-title">运行能力</h2><div class="capability-list"></div>
    </section>
    <section class="upload-panel" aria-labelledby="upload-title">
      <h2 id="upload-title">添加文档</h2>
      <div class="drop-zone" tabindex="0" role="button" aria-describedby="upload-help">
        <strong>拖拽文件到这里，或点击选择文件</strong><span id="upload-help">支持 PDF、图片和常见 Office 文档，单个文件最大 100 MB。</span>
      </div>
      <input class="file-input" type="file" aria-label="选择要上传的文档" />
      <div class="upload-status"></div>
    </section>
    <section class="document-panel" aria-labelledby="document-title">
      <div class="section-title"><div><h2 id="document-title">文档列表</h2><p class="muted">处理中项目会自动刷新状态。</p></div><button class="button button--secondary refresh-button" type="button">刷新</button></div>
      <div class="document-status" aria-live="polite"></div><ul class="document-list"></ul>
    </section>`;

  const capabilities = page.querySelector(".capability-list");
  const dropZone = page.querySelector(".drop-zone");
  const uploadHelp = page.querySelector("#upload-help");
  const fileInput = page.querySelector(".file-input");
  const uploadStatus = page.querySelector(".upload-status");
  const documentStatusNode = page.querySelector(".document-status");
  const documentList = page.querySelector(".document-list");
  let timerId = null;
  let isRefreshing = false;
  let hasLoadedDocuments = false;
  let disposed = false;

  const showUploadMessage = (message, kind = "info") => {
    uploadStatus.replaceChildren(createNotice(message, kind));
  };

  if (!ragAvailable) {
    dropZone.setAttribute("aria-disabled", "true");
    dropZone.tabIndex = -1;
    fileInput.disabled = true;
    showUploadMessage(
      ragStatus.code === "missing_model_key"
        ? "未配置模型密钥，请在项目环境变量中设置 `OPENAI_API_KEY`。"
        : "文档上传已暂停：RAG 服务尚未就绪。",
      "info",
    );
  }

  async function refreshCapabilities() {
    capabilities.replaceChildren(createNotice("正在加载运行能力…", "info"));
    try {
      const health = await getCapabilities();
      if (disposed) return;
      const details = health.capability_details || {};
      const rag = health.rag || {};
      const parser = details.parser || {};
      const values = [
        [
          "RAG 服务",
          Boolean(rag.initialized),
          rag.initialized
            ? rag.action || "RAG 服务已就绪，可以上传文档并开始问答。"
            : `未就绪：${rag.error || "尚未完成初始化"}。${rag.action || "请检查模型密钥和模型配置后重启服务。"}`,
        ],
        ["MinerU", details.mineru?.available, `${details.mineru?.reason || "状态未知"} ${details.mineru?.impact || ""}`],
        ["LibreOffice", details.libreoffice?.available, `${details.libreoffice?.reason || "状态未知"} ${details.libreoffice?.impact || ""}`],
        [
          "当前解析器",
          !parser.degraded,
          `当前实际生效：${parser.effective || health.capabilities?.parser || "未知"}。${parser.reason || ""} ${parser.impact || ""}`,
        ],
      ];
      if (details.libreoffice?.available === false) {
        uploadHelp.textContent = "支持 PDF 与图片；当前环境不支持 Office 文件，请转为 PDF 后上传。单个文件最大 100 MB。";
      }
      capabilities.replaceChildren(...values.map(([name, available, note]) => {
        const item = document.createElement("div");
        item.className = "capability";
        const state = available ? "可用" : "不可用";
        const title = document.createElement("strong");
        title.textContent = name;
        const badge = document.createElement("span");
        badge.className = `badge badge--${available ? "ready" : "muted"}`;
        badge.textContent = state;
        const description = document.createElement("small");
        description.textContent = note.trim();
        item.append(title, badge, description);
        return item;
      }));
    } catch (error) {
      if (!disposed) capabilities.replaceChildren(createNotice(`无法获取运行能力：${error.message}`));
    }
  }

  async function refreshDocuments() {
    if (isRefreshing || disposed) return;
    isRefreshing = true;
    if (!hasLoadedDocuments) {
      documentStatusNode.replaceChildren(createNotice("正在加载文档列表…", "info"));
    }
    try {
      const response = await listDocuments();
      const records = await Promise.all((response.items || []).map(async (record) => {
        if (!ACTIVE_STATUSES.has(record.status)) return record;
        try {
          return await documentStatus(record.document_id);
        } catch {
          return record;
        }
      }));
      if (!disposed) {
        renderDocuments(records);
        documentStatusNode.replaceChildren();
      }
    } catch (error) {
      if (!disposed) documentStatusNode.replaceChildren(createNotice(`无法加载文档列表：${error.message}`));
    } finally {
      hasLoadedDocuments = true;
      isRefreshing = false;
    }
  }

  function renderDocuments(records) {
    documentList.replaceChildren();
    if (!records.length) {
      const empty = document.createElement("li");
      empty.className = "empty-state";
      empty.textContent = "还没有文档。上传第一份资料后即可开始处理。";
      documentList.append(empty);
      return;
    }
    for (const record of records) {
      const row = document.createElement("li");
      row.className = "document-row";
      const details = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = record.filename;
      const metadata = document.createElement("p");
      metadata.className = "muted";
      metadata.textContent = `${formatBytes(record.size_bytes)} · ${record.media_type || "未知类型"}`;
      details.append(title, metadata);
      if (record.error) details.append(createNotice(record.error));

      const controls = document.createElement("div");
      controls.className = "document-controls";
      const status = document.createElement("span");
      status.className = `badge badge--${record.status}`;
      status.textContent = STATUS_LABELS[record.status] || record.status;
      const remove = document.createElement("button");
      remove.className = "button button--danger";
      remove.type = "button";
      remove.textContent = "删除";
      remove.addEventListener("click", async () => {
        if (!window.confirm(`确定删除“${record.filename}”吗？`)) return;
        remove.disabled = true;
        try {
          await deleteDocument(record.document_id);
          await refreshDocuments();
        } catch (error) {
          documentStatusNode.replaceChildren(createNotice(`删除失败：${error.message}`));
          remove.disabled = false;
        }
      });
      controls.append(status, remove);
      row.append(details, controls);
      documentList.append(row);
    }
  }

  async function submitFiles(files) {
    if (!ragAvailable) return;
    const selected = [...files].filter(Boolean);
    if (!selected.length) return;
    dropZone.setAttribute("aria-busy", "true");
    try {
      for (const file of selected) {
        showUploadMessage(`正在上传 ${file.name}…`);
        await uploadDocument(file);
      }
      showUploadMessage("文件已接收，正在后台处理。", "success");
      await refreshDocuments();
    } catch (error) {
      showUploadMessage(`上传失败：${error.message}`);
    } finally {
      dropZone.removeAttribute("aria-busy");
      fileInput.value = "";
    }
  }

  dropZone.addEventListener("click", () => { if (ragAvailable) fileInput.click(); });
  dropZone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (ragAvailable) fileInput.click();
    }
  });
  fileInput.addEventListener("change", () => submitFiles(fileInput.files));
  dropZone.addEventListener("dragover", (event) => { event.preventDefault(); dropZone.classList.add("is-dragging"); });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("is-dragging"));
  dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragging");
    submitFiles(event.dataTransfer?.files || []);
  });
  page.querySelector(".refresh-button").addEventListener("click", refreshDocuments);

  refreshCapabilities();
  refreshDocuments();
  timerId = window.setInterval(refreshDocuments, 3000);
  return {
    element: page,
    dispose: () => {
      disposed = true;
      window.clearInterval(timerId);
    },
  };
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "大小未知";
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
