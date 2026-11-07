/* Rotas do modo demonstração OFFLINE para o perfil de trabalho, ferramentas de ofício,
 * orçamento guiado, visita à obra e registo diário. Tudo fica no dispositivo (IndexedDB).
 * Cálculos: lib/demoTradeCalcs.js (paridade com o servidor verificada por testes). */
import catalogFx from "@/fixtures/workProfileCatalog.json";
import { CalcError, TOOLS, paintingQuoteLines, parseDaily } from "@/lib/demoTradeCalcs";

const RANK = { particulier_gratuit: 0, particulier_payant: 1, pro: 2, business: 3 };

export function workDemoRoutes({ idbGet, idbSet, ok, kind }) {
  const fail = (status, detail) => { const e = new Error(detail); e.response = { status, data: { detail }, headers: {}, config: {} }; return e; };
  const body = req => (req.data ? (typeof req.data === "string" ? JSON.parse(req.data) : req.data) : {});
  const calc = fn => { try { return ok(fn()); } catch (e) { if (e instanceof CalcError) throw fail(422, e.message); throw e; } };
  const profile = async () => ({ ...catalogFx.default_profile, ...((await idbGet("work_profile")) || {}) });
  const level = () => (kind() === "pro" ? "business" : "particulier_gratuit");

  return [
    { method: "GET", match: /^\/me\/work-profile\/catalog$/, handle: async () => ok(catalogFx) },
    { method: "GET", match: /^\/me\/work-profile$/, handle: async () => ok(await profile()) },
    { method: "PUT", match: /^\/me\/work-profile$/, handle: async req => {
        const p = { ...(await profile()), ...body(req) };
        for (const k of ["role", "org_role", "plan"]) delete p[k];
        await idbSet("work_profile", p);
        return ok(p);
      } },
    { method: "POST", match: /^\/me\/work-profile\/suggest$/, handle: async () => ok({ suggestions: [], requires_confirmation: true }) },
    { method: "GET", match: /^\/me\/work-profile\/home$/, handle: async () => {
        const p = await profile();
        const pro = kind() === "pro";
        let keys = [...(p.frequent_tasks || []), ...(p.professions || []).flatMap(x => catalogFx.profession_tasks[x] || [])];
        if (!keys.length) keys = catalogFx.generic_tasks;
        const tasks = [...new Set(keys)].map(k => ({ key: k, ...catalogFx.task_defs[k] }))
          .filter(t => (!t.feature || pro) && RANK[level()] >= RANK[t.min_level]).slice(0, 5)
          .map(t => ({ key: t.key, label: t.label, url: t.url }));
        return ok({ profile: p, tasks, continue: [], show_onboarding: p.onboarding === "pending" });
      } },
    { method: "POST", match: /^\/trade-tools\/([a-z]+)\/compute$/, handle: async (req, m) => {
        if (!TOOLS[m[1]]) throw fail(422, "Ferramenta desconhecida.");
        return calc(() => TOOLS[m[1]](body(req)));
      } },
    { method: "POST", match: /^\/guided-quote\/preview$/, handle: async req => calc(() => paintingQuoteLines(body(req).job || {})) },
    { method: "POST", match: /^\/guided-quote$/, handle: async req => calc(() => {
        const out = paintingQuoteLines(body(req).job || {});
        return { doc_id: `demo_${Date.now()}`, demo: true, duplicate: false, to_confirm: out.to_confirm, totals: out.totals };
      }) },
    { method: "GET", match: /^\/clients\/?$/, handle: async () => ok({ clients: [] }) },

    // Visita à obra
    { method: "GET", match: /^\/field\/visits\/?$/, handle: async () => ok((await idbGet("field_visits")) || []) },
    { method: "GET", match: /^\/field\/visits\/([^/]+)$/, handle: async (_r, m) => {
        const v = ((await idbGet("field_visits")) || []).find(x => x.visit_id === m[1]);
        if (!v) throw fail(404, "Visita não encontrada");
        return ok(v);
      } },
    ...["POST", "PUT"].map(method => ({ method, match: method === "POST" ? /^\/field\/visits\/?$/ : /^\/field\/visits\/([^/]+)$/, handle: async (req, m) => {
        const b = body(req);
        const list = (await idbGet("field_visits")) || [];
        const missing = [];
        if (!b.address) missing.push("Morada da obra");
        for (const x of b.measures || []) {
          if (x.value === "" || x.value == null) missing.push(`Medida em falta: ${x.label}`);
          else if (x.source === "estimado") missing.push(`Medida estimada a confirmar: ${x.label}`);
        }
        for (const q of b.questions || []) if (!q.answered) missing.push(`Pergunta pendente: ${q.text}`);
        const summary = b.summary || [`Visita: ${b.title || "Visita à obra"}`, b.address, b.access && `Acessos: ${b.access}`, b.demolitions && `Demolições: ${b.demolitions}`,
          b.protections && `Proteção de espaços: ${b.protections}`, b.notes && `Notas: ${b.notes}`,
          ...(b.measures || []).map(x => `- ${x.label}: ${x.value === "" || x.value == null ? "por medir" : `${x.value} ${x.unit || "m"}`}`)].filter(Boolean).join("\n");
        const id = m?.[1] || `vis_demo_${Date.now()}`;
        const v = { ...b, visit_id: id, title: b.title || "Visita à obra", summary, summary_edited: !!b.summary, to_confirm: missing, updated_at: new Date().toISOString() };
        await idbSet("field_visits", [v, ...list.filter(x => x.visit_id !== id)]);
        return ok(v);
      } })),

    // Registo diário
    { method: "POST", match: /^\/field\/daily\/parse$/, handle: async req => calc(() => parseDaily(body(req).text)) },
    { method: "GET", match: /^\/field\/daily\/?$/, handle: async () => ok((await idbGet("field_daily")) || []) },
    { method: "POST", match: /^\/field\/daily\/?$/, handle: async req => {
        const b = body(req);
        if (!b.confirmed) throw fail(422, "Confirme o registo antes de o guardar.");
        const list = (await idbGet("field_daily")) || [];
        const rec = { ...b, log_id: `dia_demo_${Date.now()}`, created_at: new Date().toISOString() };
        await idbSet("field_daily", [rec, ...list]);
        return ok(rec);
      } },
  ];
}
