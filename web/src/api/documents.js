import { api } from "./client.js";

export const listDocuments = () => api("/documents");
export const documentStatus = (id) => api(`/documents/${encodeURIComponent(id)}/status`);
export const deleteDocument = (id) =>
  api(`/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
export const getCapabilities = () => api("/healthz");

export async function uploadDocument(file) {
  if (!(file instanceof File)) throw new TypeError("请选择要上传的文件");
  const body = new FormData();
  body.append("file", file, file.name);
  return api("/documents", { method: "POST", body });
}
