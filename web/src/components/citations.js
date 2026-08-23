export function createCitations(items = []) {
  const details = document.createElement("details");
  details.className = "citations";
  const summary = document.createElement("summary");
  summary.textContent = `引用来源（${items.length}）`;
  details.append(summary);

  if (items.length === 0) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "本次回答未返回可展示的引用来源。";
    details.append(empty);
    return details;
  }

  const list = document.createElement("ul");
  for (const item of items) {
    const row = document.createElement("li");
    const source = item.document_id || "未命名文档";
    const kind = item.kind || "片段";
    const preview = item.preview || item.id || "无摘要";
    row.textContent = `${source} · ${kind}：${preview}`;
    list.append(row);
  }
  details.append(list);
  return details;
}
