import { api } from "@/lib/api";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Lance un traitement long côté serveur (background=1) puis interroge la tâche jusqu'à la fin.
export async function runCotesJob(path, body, { maxMs = 600000, onTick } = {}) {
  const { data } = await api.post(`${path}?background=1`, body);
  if (!data.job_id) return data;
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs) {
    await sleep(2500);
    const { data: j } = await api.get(`/takeoffs/cotes-jobs/${data.job_id}`);
    onTick?.(Math.round((Date.now() - t0) / 1000));
    if (j.status === "done") return j.result;
    if (j.status === "error") throw new Error(j.error || "Traitement impossible");
  }
  throw new Error("Délai dépassé — réessayez");
}
