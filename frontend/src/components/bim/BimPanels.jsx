// Painéis do BIM Studio: propriedades do elemento, medições, orçamento e versões.
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, eur2 } from "@/lib/api";
import { CONFIDENCE_STYLE, ORIGIN_STYLE, formatQty } from "./bimGeometry";

const BTN = "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition disabled:opacity-50";
export const BTN_PRIMARY = `${BTN} bg-primary text-primary-foreground hover:opacity-90`;
export const BTN_GHOST = `${BTN} border border-border hover:bg-accent`;
const BTN_COPPER = `${BTN} bg-[#c4733f] text-white hover:bg-[#a95f31]`;

export function OriginBadge({ q, simple }) {
  if (!q) return <span className="text-[11px] rounded-full px-2 py-0.5 bg-red-500/15 text-red-700 dark:text-red-300">Em falta</span>;
  const s = ORIGIN_STYLE[q.origin] || ORIGIN_STYLE.estimated;
  return (
    <span title={`${s.label} — ${q.source || ""}`} className={`text-[11px] rounded-full border px-2 py-0.5 ${s.cls}`}>
      {q.verified ? "✓ Verificada" : simple && q.origin === "estimated" ? "Aproximada" : s.short}
    </span>
  );
}

// ── Painel do elemento selecionado ──────────────────────────────────────────
export function ElementPanel({ base, gid, profile, canEdit, onChanged, onHide, onIsolate }) {
  const [el, setEl] = useState(null);
  const [edit, setEdit] = useState({});
  const simple = profile === "simples";
  const technical = profile === "engenheiro";

  useEffect(() => {
    setEl(null);
    if (gid) api.get(`${base}/elements/${gid}`).then(({ data }) => setEl(data)).catch(() => setEl(null));
  }, [base, gid]);

  if (!gid) return <p className="text-sm text-muted-foreground p-4">Clique num elemento do modelo para ver as suas propriedades e medições.</p>;
  if (!el) return <p className="text-sm text-muted-foreground p-4">A carregar…</p>;

  const save = async (body) => {
    try {
      const { data } = await api.patch(`${base}/elements/${gid}`, body);
      setEl(data);
      setEdit({});
      onChanged?.();
      toast.success("Medição atualizada");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Não foi possível guardar");
    }
  };

  return (
    <div className="p-4 space-y-4 text-sm" data-testid="bim-element-panel">
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{el.category_label}</p>
        <h3 className="font-semibold text-base leading-tight">{el.name || el.ifc_class}</h3>
        <p className="text-xs text-muted-foreground">{el.storey || "Sem piso"}{el.type_name ? ` · ${el.type_name}` : ""}</p>
        {!simple && <p className="text-[11px] text-muted-foreground mt-1 font-mono">{el.ifc_class} · {el.gid}</p>}
        {el.container_note && <p className="mt-2 text-xs rounded-lg bg-accent px-2 py-1">{el.container_note}</p>}
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={BTN_GHOST} onClick={() => onHide?.(gid)}>Ocultar</button>
        <button type="button" className={BTN_GHOST} onClick={() => onIsolate?.(gid)}>Isolar</button>
        {canEdit && el.counted && (
          <button type="button" className={BTN_GHOST} onClick={() => save({ included: !el.included })} data-testid="bim-toggle-include">
            {el.included ? "Excluir das medições" : "Incluir nas medições"}
          </button>
        )}
      </div>
      {el.materials?.length > 0 && <p><span className="text-muted-foreground">Materiais:</span> {el.materials.join(", ")}</p>}
      {el.missing?.length > 0 && (
        <p className="rounded-lg bg-red-500/10 text-red-700 dark:text-red-300 px-2 py-1 text-xs">
          Dados em falta: {el.missing.map((m) => (m === "material" ? "material" : el.quantities?.[m]?.label || m)).join(", ")}
        </p>
      )}
      <div>
        <h4 className="font-medium mb-1">Medições</h4>
        <table className="w-full text-xs">
          <tbody>
            {Object.entries(el.quantities || {}).filter(([k]) => technical || !["section_area", "surface_area", "perimeter"].includes(k)).map(([k, q]) => (
              <tr key={k} className="border-t border-border">
                <td className="py-1.5 pr-2">{q.label}</td>
                <td className="py-1.5 pr-2 text-right font-medium whitespace-nowrap">
                  {edit[k] !== undefined ? (
                    <input type="number" min="0" step="any" value={edit[k]} autoFocus
                           onChange={(e) => setEdit({ ...edit, [k]: e.target.value })}
                           className="w-24 rounded border border-border bg-background px-1 py-0.5 text-right" />
                  ) : formatQty(q.value, q.unit)}
                </td>
                <td className="py-1.5"><OriginBadge q={q} simple={simple} /></td>
                {canEdit && (
                  <td className="py-1.5 text-right whitespace-nowrap">
                    {edit[k] !== undefined ? (
                      <>
                        <button type="button" className="text-primary mr-2" onClick={() => save({ quantities: { [k]: { value: Number(edit[k]), note: "correção no BIM Studio" } } })}>Guardar</button>
                        <button type="button" className="text-muted-foreground" onClick={() => setEdit({})}>×</button>
                      </>
                    ) : (
                      <>
                        {!q.verified && <button type="button" className="text-primary mr-2" title="Confirmo que esta medição está correta" onClick={() => save({ validate: [k] })}>Validar</button>}
                        <button type="button" className="text-muted-foreground mr-2" onClick={() => setEdit({ [k]: q.value })}>Corrigir</button>
                        {q.origin === "manual" && <button type="button" className="text-muted-foreground" onClick={() => save({ quantities: { [k]: { reset: true } } })}>Repor</button>}
                      </>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {!simple && <p className="text-[11px] text-muted-foreground mt-1">Passe o rato sobre a origem para ver a fonte exata (Qto IFC, geometria…).</p>}
      </div>
      {!simple && Object.keys(el.properties || {}).length > 0 && (
        <details open={technical}>
          <summary className="cursor-pointer font-medium">Propriedades IFC</summary>
          {Object.entries(el.properties).map(([pset, props]) => (
            <div key={pset} className="mt-2">
              <p className="text-xs font-semibold">{pset}</p>
              <dl className="grid grid-cols-2 gap-x-2 text-xs">
                {Object.entries(props).map(([k, v]) => (
                  <div key={k} className="contents"><dt className="text-muted-foreground truncate">{k}</dt><dd className="truncate">{String(v)}</dd></div>
                ))}
              </dl>
            </div>
          ))}
        </details>
      )}
    </div>
  );
}

// ── Separador Medições ──────────────────────────────────────────────────────
export function MeasurementsTab({ base, version, categories, profile, onSelect, refreshKey }) {
  const [rows, setRows] = useState({ items: [], total: 0 });
  const [f, setF] = useState({ category: "", storey: "", q: "", missing: false, skip: 0 });
  const simple = profile === "simples";
  useEffect(() => {
    const p = new URLSearchParams({ limit: "100", skip: String(f.skip) });
    if (f.category) p.set("category", f.category);
    if (f.storey) p.set("storey", f.storey);
    if (f.q) p.set("q", f.q);
    if (f.missing) p.set("missing", "true");
    api.get(`${base}/elements?${p}`).then(({ data }) => setRows(data)).catch(() => toast.error("Não foi possível carregar as medições"));
  }, [base, f, refreshKey]);
  return (
    <div className="space-y-3" data-testid="bim-measurements">
      {simple && <p className="text-sm rounded-lg bg-accent px-3 py-2">Verde = calculado a partir do desenho · Azul = indicado pelo projetista · Amarelo = aproximação a confirmar · Vermelho = falta informação.</p>}
      <div className="flex flex-wrap gap-2 items-center text-sm">
        <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value, skip: 0 })} className="rounded-lg border border-border bg-background px-2 py-1.5">
          <option value="">Todas as categorias</option>
          {Object.entries(categories || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={f.storey} onChange={(e) => setF({ ...f, storey: e.target.value, skip: 0 })} className="rounded-lg border border-border bg-background px-2 py-1.5">
          <option value="">Todos os pisos</option>
          {(version.storeys || []).map((s) => <option key={s.gid} value={s.gid}>{s.name}</option>)}
        </select>
        <input placeholder="Procurar por nome…" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, skip: 0 })} className="rounded-lg border border-border bg-background px-2 py-1.5" />
        <label className="flex items-center gap-1"><input type="checkbox" checked={f.missing} onChange={(e) => setF({ ...f, missing: e.target.checked, skip: 0 })} /> Só com dados em falta</label>
        <span className="text-muted-foreground ml-auto">{rows.total} elemento(s)</span>
      </div>
      <div className="overflow-x-auto rounded-xl border">
        <table className="min-w-full text-sm">
          <thead className="bg-accent/60 text-left">
            <tr><th className="p-2">Elemento</th><th className="p-2">Piso</th><th className="p-2 text-right">Medição principal</th><th className="p-2">Origem</th>{!simple && <th className="p-2">Classe IFC</th>}<th className="p-2" /></tr>
          </thead>
          <tbody>
            {rows.items.map((e) => {
              const q = e.quantities?.[e.primary_key];
              return (
                <tr key={e.gid} className={`border-t border-border hover:bg-accent/40 cursor-pointer ${!e.included ? "opacity-50" : ""}`} onClick={() => onSelect(e.gid)}>
                  <td className="p-2"><div className="font-medium">{e.name || e.ifc_class}</div><div className="text-xs text-muted-foreground">{e.category_label}</div></td>
                  <td className="p-2 text-xs">{e.storey || "—"}</td>
                  <td className="p-2 text-right whitespace-nowrap">{q ? formatQty(q.value, q.unit) : "—"}</td>
                  <td className="p-2">{e.counted ? <OriginBadge q={q} simple={simple} /> : <span className="text-[11px] text-muted-foreground">nos sub-elementos</span>}</td>
                  {!simple && <td className="p-2 text-xs font-mono">{e.ifc_class}</td>}
                  <td className="p-2 text-xs">{e.missing?.length > 0 && <span className="text-red-600">⚠ {e.missing.length}</span>}{!e.counted && <span className="text-muted-foreground">agregador</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex gap-2 justify-end">
        <button type="button" className={BTN_GHOST} disabled={f.skip === 0} onClick={() => setF({ ...f, skip: Math.max(0, f.skip - 100) })}>Anterior</button>
        <button type="button" className={BTN_GHOST} disabled={f.skip + 100 >= rows.total} onClick={() => setF({ ...f, skip: f.skip + 100 })}>Seguinte</button>
      </div>
    </div>
  );
}

// ── Separador Orçamento ─────────────────────────────────────────────────────
export function BudgetTab({ base, canEdit, profile, onHighlight, refreshKey }) {
  const [groups, setGroups] = useState([]);
  const [library, setLibrary] = useState([]);
  const [budget, setBudget] = useState(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const simple = profile === "simples";

  const load = () => Promise.all([
    api.get(`${base}/groups`).then(({ data }) => setGroups(data.groups || [])),
    api.get(`${base}/budget`).then(({ data }) => setBudget(data)),
  ]).catch(() => toast.error("Não foi possível carregar o orçamento"));

  useEffect(() => { load(); api.get("/bim/library").then(({ data }) => setLibrary(data.items || [])).catch(() => {}); /* eslint-disable-next-line */ }, [base, refreshKey]);

  const itemsById = useMemo(() => Object.fromEntries(library.map((i) => [i.item_id, i])), [library]);

  const suggest = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`${base}/mappings/suggest`);
      toast.success(`${data.suggested} sugestão(ões) — confirme cada uma antes de orçamentar`);
      await load();
    } catch (err) { toast.error(err?.response?.data?.detail || "Sugestão impossível"); } finally { setBusy(false); }
  };
  const setMapping = async (g, body) => {
    try {
      await api.put(`${base}/mappings`, { group_key: g.group_key, ...body });
      await load();
    } catch (err) { toast.error(err?.response?.data?.detail || "Associação impossível"); }
  };
  const createQuote = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`${base}/budget/quote`, {});
      toast.success("Orçamento criado — reveja-o no editor");
      navigate(`/devis-editeur/${data.doc_id}`);
    } catch (err) { toast.error(err?.response?.data?.detail || "Não foi possível criar o orçamento"); } finally { setBusy(false); }
  };
  const exportUrl = (fmt) => `${process.env.REACT_APP_BACKEND_URL}/api${base}/export.${fmt}`;

  return (
    <div className="space-y-4" data-testid="bim-budget">
      <div className="flex flex-wrap gap-2 items-center">
        {canEdit && <button type="button" className={BTN_GHOST} onClick={suggest} disabled={busy} data-testid="bim-suggest-btn">Sugerir artigos da biblioteca</button>}
        <a className={BTN_GHOST} href={exportUrl("xlsx")}>Mapa de quantidades (Excel)</a>
        <a className={BTN_GHOST} href={exportUrl("csv")}>CSV</a>
        {canEdit && <button type="button" className={`${BTN_COPPER} ml-auto`} onClick={createQuote} disabled={busy || !budget?.lines?.length} data-testid="bim-create-quote-btn">Gerar orçamento editável</button>}
      </div>
      <p className="text-xs text-muted-foreground">
        {simple ? "Escolha para cada grupo o trabalho correspondente da sua lista de preços. Só os grupos confirmados entram no orçamento."
          : "Preços exclusivamente da biblioteca da empresa. As sugestões são heurísticas (palavras-chave + unidade) e só contam depois de confirmadas."}
      </p>
      <div className="overflow-x-auto rounded-xl border">
        <table className="min-w-full text-sm">
          <thead className="bg-accent/60 text-left">
            <tr><th className="p-2">Grupo de elementos</th><th className="p-2 text-right">Quantidade</th><th className="p-2">Fiabilidade</th><th className="p-2">Artigo associado</th><th className="p-2" /></tr>
          </thead>
          <tbody>
            {groups.map((g) => {
              const m = g.mapping;
              const qkey = m?.quantity_key || g.primary_key;
              const unit = { area: "m²", volume: "m³", length: "m", count: "u", weight: "kg" }[qkey];
              return (
                <tr key={g.group_key} className="border-t border-border align-top">
                  <td className="p-2"><div className="font-medium">{g.label}</div><div className="text-xs text-muted-foreground">{g.category_label}{g.material ? ` · ${g.material}` : ""} · {g.included} el.</div></td>
                  <td className="p-2 text-right whitespace-nowrap">{formatQty(g.totals?.[qkey], unit)}{g.missing?.[qkey] ? <div className="text-[11px] text-red-600">{g.missing[qkey]} sem medição</div> : null}</td>
                  <td className="p-2"><span className={`text-[11px] rounded-full px-2 py-0.5 ${CONFIDENCE_STYLE[g.confidence] || ""}`}>{g.confidence}</span></td>
                  <td className="p-2 min-w-[260px]">
                    {canEdit ? (
                      <select value={m?.item_id || ""} onChange={(e) => setMapping(g, { item_id: e.target.value || null, status: e.target.value ? "confirmed" : "none" })}
                              className="w-full rounded-lg border border-border bg-background px-2 py-1 text-xs">
                        <option value="">— sem artigo —</option>
                        {library.map((i) => <option key={i.item_id} value={i.item_id}>{i.designation} ({i.unit} · {eur2(i.unit_price_ht)})</option>)}
                      </select>
                    ) : <span className="text-xs">{itemsById[m?.item_id]?.designation || "—"}</span>}
                    {m?.status === "suggested" && <p className="text-[11px] text-amber-700 dark:text-amber-300 mt-1" title={m.reason}>Sugestão (não confirmada): {m.reason}</p>}
                  </td>
                  <td className="p-2 whitespace-nowrap">
                    {canEdit && m?.status === "suggested" && m.item_id && <button type="button" className="text-primary text-xs mr-2" onClick={() => setMapping(g, { item_id: m.item_id, status: "confirmed" })}>Confirmar</button>}
                    {m?.status === "confirmed" && <span className="text-xs text-emerald-700">✓ confirmada</span>}
                    <button type="button" className="text-xs ml-2 text-[#c4733f]" onClick={() => onHighlight?.(g.gids)}>Ver no 3D</button>
                    {canEdit && <button type="button" className="text-muted-foreground text-xs ml-2" onClick={() => setMapping(g, { item_id: null, status: "none", excluded: !m?.excluded })}>{m?.excluded ? "Reincluir" : "Fora do orçamento"}</button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {budget && (
        <div className="grid md:grid-cols-3 gap-4">
          <div className="rounded-xl border p-4">
            <p className="text-xs text-muted-foreground">Total s/IVA (associações confirmadas)</p>
            <p className="text-2xl font-semibold" data-testid="bim-budget-total">{eur2(budget.total_ht)}</p>
            <p className="text-xs text-muted-foreground mt-1">{budget.lines.length} linha(s) · {budget.unmapped.length} grupo(s) por associar</p>
          </div>
          <div className="rounded-xl border p-4 text-sm"><p className="font-medium mb-1">Por categoria</p>{Object.entries(budget.subtotals_by_category).map(([k, v]) => <div key={k} className="flex justify-between"><span>{k}</span><span>{eur2(v)}</span></div>)}</div>
          <div className="rounded-xl border p-4 text-sm"><p className="font-medium mb-1">Por piso</p>{Object.entries(budget.subtotals_by_storey).map(([k, v]) => <div key={k} className="flex justify-between"><span>{k}</span><span>{eur2(v)}</span></div>)}</div>
          {budget.warnings.length > 0 && (
            <ul className="md:col-span-3 rounded-xl border border-amber-300 bg-amber-50 dark:bg-amber-950/30 p-3 text-xs list-disc pl-6">
              {budget.warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// ── Separador Versões ───────────────────────────────────────────────────────
export function VersionsTab({ model, canEdit, onUploadVersion, onOpenVersion }) {
  const versions = model?.versions || [];
  const done = versions.filter((v) => v.status === "done");
  const [ab, setAb] = useState({ a: done[1]?.version || "", b: done[0]?.version || "" });
  const [diff, setDiff] = useState(null);
  const run = () => api.get(`/bim/models/${model.model_id}/compare?a=${ab.a}&b=${ab.b}`).then(({ data }) => setDiff(data)).catch((e) => toast.error(e?.response?.data?.detail || "Comparação impossível"));
  const download = async (v) => {
    const { data } = await api.get(`/bim/models/${model.model_id}/versions/${v}/download-url`);
    window.location.href = `${process.env.REACT_APP_BACKEND_URL}${data.url}`;
  };
  return (
    <div className="space-y-4" data-testid="bim-versions">
      {canEdit && <button type="button" className={BTN_PRIMARY} onClick={onUploadVersion}>Carregar nova versão do modelo</button>}
      <table className="min-w-full text-sm rounded-xl border">
        <thead className="bg-accent/60 text-left"><tr><th className="p-2">Versão</th><th className="p-2">Ficheiro</th><th className="p-2">Estado</th><th className="p-2">Elementos</th><th className="p-2">Duração</th><th className="p-2" /></tr></thead>
        <tbody>
          {versions.map((v) => (
            <tr key={v.version} className="border-t border-border">
              <td className="p-2 font-medium">v{v.version}</td><td className="p-2 text-xs">{v.filename}</td><td className="p-2 text-xs">{v.stage || v.status}</td>
              <td className="p-2 text-xs">{v.stats?.elements ?? "—"}</td><td className="p-2 text-xs">{v.duration_s != null ? `${v.duration_s} s` : "—"}</td>
              <td className="p-2 text-xs whitespace-nowrap"><button type="button" className="text-primary mr-2" onClick={() => onOpenVersion(v.version)}>Abrir</button><button type="button" className="text-muted-foreground" onClick={() => download(v.version)}>Descarregar IFC</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {done.length >= 2 && (
        <div className="rounded-xl border p-4 space-y-3">
          <div className="flex flex-wrap gap-2 items-center text-sm">
            Comparar
            <select value={ab.a} onChange={(e) => setAb({ ...ab, a: e.target.value })} className="rounded-lg border border-border bg-background px-2 py-1">{done.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}</select>
            com
            <select value={ab.b} onChange={(e) => setAb({ ...ab, b: e.target.value })} className="rounded-lg border border-border bg-background px-2 py-1">{done.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}</select>
            <button type="button" className={BTN_GHOST} onClick={run}>Comparar</button>
          </div>
          {diff && (
            <div className="text-sm space-y-2">
              <p>{diff.summary.added} adicionado(s) · {diff.summary.removed} removido(s) · {diff.summary.changed} alterado(s) · {diff.summary.unchanged} sem alterações</p>
              {["added", "removed", "changed"].map((k) => diff[k].length > 0 && (
                <details key={k}><summary className="cursor-pointer">{{ added: "Adicionados", removed: "Removidos", changed: "Alterados" }[k]}</summary>
                  <ul className="text-xs list-disc pl-5">{diff[k].slice(0, 100).map((e) => <li key={e.gid}>{e.name || e.gid} — {e.storey || "sem piso"}{e.changes ? ` (${Object.entries(e.changes).map(([q, c]) => `${q}: ${c.before ?? "—"} → ${c.after ?? "—"}`).join("; ")})` : ""}</li>)}</ul>
                </details>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
