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
    if (j.status === "error") throw new Error(j.error || "Tratamento impossível");
  }
  throw new Error("Prazo ultrapassado — tente novamente");
}

// Lot 51 : analyse IA d'une page de plan en tâche de fond (plus de 524 sur les gros plans).
export async function runPlanAnalysis(planId, pageIndex) {
  const { data } = await api.post(`/takeoffs/${planId}/analyze?page_index=${pageIndex}&background=1`);
  if (!data || !data.job_id) return { data };
  return { data: await pollCotesJob(data.job_id, { timeoutMs: 330000 }) };
}

export async function pollCotesJob(jobId, { timeoutMs = 600000 } = {}) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    await sleep(4000);
    const { data: j } = await api.get(`/takeoffs/cotes-jobs/${jobId}`);
    if (j.status === "done") return j.result;
    if (j.status === "error") throw new Error(j.error || "Tratamento impossível");
  }
  throw new Error("Prazo ultrapassado");
}
