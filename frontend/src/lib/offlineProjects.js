// Offline-aware project reads/writes for the "Mode chantier hors connexion".
import { api } from "@/lib/api";
import { snapSet, snapGet, queueAdd, queueList, queueRemove } from "@/lib/offlineStore";

export const isOnline = () => (typeof navigator === "undefined" ? true : navigator.onLine);

// ---- Reads (cache-through) ----
export async function fetchProjects(userId) {
  if (isOnline()) {
    try {
      const { data } = await api.get("/projects");
      const list = Array.isArray(data) ? data : [];
      await snapSet(userId, "projects", list);
      return { list, offline: false };
    } catch (e) {
      if (isOnline()) throw e; // real error, not a connectivity drop
    }
  }
  const cached = await snapGet(userId, "projects");
  return { list: Array.isArray(cached) ? cached : [], offline: true };
}

export async function fetchProject(userId, id) {
  if (isOnline()) {
    try {
      const { data } = await api.get(`/projects/${id}`);
      await upsertCachedProject(userId, data);
      return { project: data, offline: false };
    } catch (e) {
      if (isOnline()) throw e;
    }
  }
  const cached = await snapGet(userId, "projects");
  const project = (Array.isArray(cached) ? cached : []).find((p) => p.project_id === id) || null;
  return { project, offline: true };
}

async function upsertCachedProject(userId, project) {
  const cached = await snapGet(userId, "projects");
  const list = Array.isArray(cached) ? cached.slice() : [];
  const idx = list.findIndex((p) => p.project_id === project.project_id);
  if (idx >= 0) list[idx] = project; else list.push(project);
  await snapSet(userId, "projects", list);
}

// ---- Writes (progress / notes) with offline queue ----
// patch example: { progress: {...} } or { notes: "..." }
export async function patchProject(userId, id, patch, label = "") {
  if (isOnline()) {
    const { data } = await api.patch(`/projects/${id}`, patch);
    await upsertCachedProject(userId, data);
    return { project: data, queued: false };
  }
  // Offline: optimistic local update + queue the mutation.
  const cached = await snapGet(userId, "projects");
  const list = Array.isArray(cached) ? cached.slice() : [];
  const idx = list.findIndex((p) => p.project_id === id);
  let project = idx >= 0 ? { ...list[idx], ...patch, updated_at: new Date().toISOString() } : null;
  if (project) { list[idx] = project; await snapSet(userId, "projects", list); }
  await queueAdd({ userId, method: "patch", url: `/projects/${id}`, body: patch, entity: id, label });
  if (typeof window !== "undefined") window.dispatchEvent(new Event("construpilot-offline-queued"));
  return { project, queued: true };
}

export async function pendingCount(userId) {
  return (await queueList(userId)).length;
}

// Queue a chantier photo upload while offline (stored as Blob in IndexedDB).
export async function uploadProjectPhoto(userId, projectId, file, fields = {}) {
  const url = `/projects/${projectId}/photos`;
  if (isOnline()) {
    const fd = new FormData();
    fd.append("file", file);
    Object.entries(fields).forEach(([k, v]) => { if (v != null && v !== "") fd.append(k, v); });
    const { data } = await api.post(url, fd, { headers: { "Content-Type": "multipart/form-data" } });
    return { data, queued: false };
  }
  await queueAdd({ userId, kind: "upload", url, entity: projectId, file, fileName: file.name || "photo.jpg", fields, label: "Fotografia da obra" });
  if (typeof window !== "undefined") window.dispatchEvent(new Event("construpilot-offline-queued"));
  return { data: null, queued: true };
}

// Replay queued mutations in order. Returns number successfully synced.
export async function flushQueue(userId) {
  if (!isOnline()) return 0;
  const items = (await queueList(userId)).sort((a, b) => a.ts - b.ts);
  let done = 0;
  for (const it of items) {
    try {
      if (it.kind === "upload") {
        const fd = new FormData();
        fd.append("file", it.file, it.fileName || "photo.jpg");
        Object.entries(it.fields || {}).forEach(([k, v]) => { if (v != null && v !== "") fd.append(k, v); });
        await api.post(it.url, fd, { headers: { "Content-Type": "multipart/form-data" } });
      } else if (it.method === "patch") {
        const { data } = await api.patch(it.url, it.body);
        if (data?.project_id) await upsertCachedProject(userId, data);
      }
      await queueRemove(it.id);
      done += 1;
    } catch {
      break; // stop at first failure; keep order for next attempt
    }
  }
  if (done > 0) {
    try { const { data } = await api.get("/projects"); await snapSet(userId, "projects", Array.isArray(data) ? data : []); } catch { /* ignore */ }
  }
  return done;
}
