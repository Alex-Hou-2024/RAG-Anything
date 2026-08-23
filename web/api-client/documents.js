export async function api(path, options={}) { const r=await fetch(path,options); if(!r.ok) throw new Error((await r.json().catch(()=>({}))).error?.message||r.statusText); return r.status===204?null:r.json(); }
export const listDocuments=()=>api('/documents'); export const status=id=>api(`/documents/${id}/status`); export const remove=id=>api(`/documents/${id}`,{method:'DELETE'}); export const capabilities=()=>api('/healthz');
export const upload=file=>{const f=new FormData();f.append('file',file);return api('/documents',{method:'POST',body:f});};
