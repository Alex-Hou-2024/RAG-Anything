import { api } from "./client.js";
import { publicUrl } from "./base-url.js";

export const listDocuments = () => api("documents");
export const documentStatus = (id) => api(`documents/${encodeURIComponent(id)}/status`);
export const deleteDocument = (id) =>
  api(`documents/${encodeURIComponent(id)}`, { method: "DELETE" });

export async function getCapabilities() {
  const response = await fetch(publicUrl("healthz"), {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`无法获取运行能力（${response.status}）`);
  }
  return response.json();
}

export async function uploadDocument(file) {
  if (!(file instanceof File)) throw new TypeError("请选择要上传的文件");
  const body = new FormData();
  body.append("file", file, file.name);
  return api("documents", { method: "POST", body });
}
