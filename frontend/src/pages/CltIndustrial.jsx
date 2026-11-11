import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import CltConfirmation from "@/components/bim/CltConfirmation";

const base = "/clt-industrial";
const input = "w-full rounded border bg-background px-2 py-1.5 text-sm";
const button = "rounded bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50";
const secondary = "rounded border px-3 py-2 text-sm";
const units = ["m3", "m2", "m", "kg", "h", "un", "viagem", "lote", "L", "kWh", "km", "dia"];
const stages = { compra: "Compra", producao: "Produção", transporte: "Transporte", montagem: "Montagem", entrega: "Entrega" };
const kinds = { declared_area: "Área indicada", ceiling_height: "Pé-direito", opening_dimensions: "Vão indicado", material_note: "Material indicado" };
const euros = new Intl.NumberFormat("pt-PT", { style: "currency", currency: "EUR" });
const decimal = new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 6 });
const fmt = (v) => v == null ? "Por apurar" : euros.format(v);
const errText = (e) => typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Verifique os valores e as permissões da conta.";

function Field({ label, children }) {
  return <label className="grid gap-1 text-sm"><span>{label}</span>{children}</label>;
}

function Evidence({ file, report }) {
  const [number, setNumber] = useState(1);
  const [selected, setSelected] = useState(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const page = report.pages[number - 1];
  const mark = page.evidence.find((item) => item.id === selected);
  const review = page.review;
  const hasReview = report.pages.some((sheet) => sheet.review);
  const reviewMarkers = review?.markers || [];
  const overlays = reviewMarkers.length ? reviewMarkers : (mark ? [{ ...mark, status: "pending" }] : []);
  useEffect(() => {
    const controller = new AbortController();
    let previewUrl;
    setUrl("");
    setError("");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("page", number);
    api.post(`${base}/pdf/preview`, fd, { responseType: "blob", signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      previewUrl = URL.createObjectURL(data);
      setUrl(previewUrl);
    }).catch(() => { if (!controller.signal.aborted) setError("Não foi possível carregar a folha."); });
    return () => { controller.abort(); if (previewUrl) URL.revokeObjectURL(previewUrl); };
  }, [file, number]);
  return <div className="grid gap-4">
    <div className="flex flex-wrap items-center gap-3">
      <strong>{file.name}</strong>
      <Field label="Folha"><select className={input} value={number} onChange={(e) => { setNumber(Number(e.target.value)); setSelected(null); }}>
        {report.pages.map((p) => <option key={p.page} value={p.page}>{p.review?.floor || `${p.page} de ${report.pages.length}`}</option>)}
      </select></Field>
    </div>
    {hasReview && <div className="overflow-x-auto rounded border p-3">
      <h2 className="mb-2 font-semibold">Medições por piso</h2>
      <table className="w-full text-left text-sm">
        <thead><tr><th>Piso</th><th>CLT em planta</th><th>Volume CLT</th><th>Base interior declarada</th><th>Área de revestimento</th><th>Volume de revestimento</th></tr></thead>
        <tbody>{report.pages.filter((p) => p.review?.in_scope).map((p) => <tr key={p.page} className="border-t">
          <th><button type="button" className="py-2 underline" onClick={() => { setNumber(p.page); setSelected(null); }}>{p.review.floor}</button></th>
          {[
            [p.review.clt_plan_m2, "m²"], [p.review.clt_volume_m3, "m³"], [p.review.interior_base_m2, "m²"],
            [p.review.finish_area_m2, "m²"], [p.review.finish_volume_m3, "m³"],
          ].map(([v, unit], i) => <td key={i} className="pr-3">{v == null ? "Por confirmar" : `${decimal.format(Number(v.toFixed(2)))} ${unit}`}</td>)}
        </tr>)}</tbody>
      </table>
      <p className="mt-2 text-sm"><span className="text-emerald-700 dark:text-emerald-400">Verde: medido em planta</span> · <span className="text-sky-700 dark:text-sky-400">Azul: área declarada</span> · <span className="text-amber-700 dark:text-amber-400">Âmbar: associação por confirmar</span></p>
    </div>}
    <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(250px,2fr)]">
      {url ? <div className="relative self-start overflow-hidden rounded border">
        <img src={url} alt={`Folha ${number} do desenho`} className="block w-full" />
        {overlays.map((item) => <span key={item.id} aria-hidden="true" className={`pointer-events-none absolute border ${item.id === selected ? "z-10 border-2" : ""} ${
          item.status === "measured" ? "border-emerald-600 bg-emerald-400/30" :
          item.status === "declared" ? "border-sky-600 bg-sky-400/30" : "border-amber-500 bg-amber-400/25"}`}
          style={{
          left: `${item.rect[0] * 100}%`, top: `${item.rect[1] * 100}%`,
          width: `${(item.rect[2] - item.rect[0]) * 100}%`, height: `${(item.rect[3] - item.rect[1]) * 100}%`,
        }} />)}
      </div> : <p role="status">{error || "A carregar a folha…"}</p>}
      <div>
        {review && <div className="mb-4 grid gap-2 text-sm">
          <h2 className="font-semibold">Conferência · {review.floor}</h2>
          {review.notes.map((note) => <p key={note}>{note}</p>)}
          {reviewMarkers.some((m) => m.status === "measured") && <Field label="Localizar troço ou cota de escala">
            <select className={input} value={reviewMarkers.some((m) => m.id === selected && m.status === "measured") ? selected : ""}
              onChange={(e) => setSelected(e.target.value || null)}>
              <option value="">Selecionar</option>
              {reviewMarkers.filter((m) => m.status === "measured").map((m) => <option key={m.id} value={m.id}>{m.label} · {m.id}</option>)}
            </select>
          </Field>}
        </div>}
        <h2 className="font-semibold">Referências na folha {number}</h2>
        <p className="mb-2 text-sm text-muted-foreground">Selecione uma referência para localizar a origem no desenho. As anotações precisam de revisão antes de servir de base ao fabrico.</p>
        {!page.evidence.length && <p>Sem cotas ou anotações reconhecidas automaticamente nesta folha.</p>}
        <ul className="grid gap-2">
          {page.evidence.map((item) => <li key={item.id}><button type="button" aria-pressed={selected === item.id}
            className="w-full rounded border px-2 py-1.5 text-left text-sm aria-pressed:border-primary"
            onClick={() => setSelected(item.id)}>
            <strong>{kinds[item.kind]}</strong><br />
            {item.text}
            {item.requires_unit_confirmation && <span className="block text-muted-foreground">Confirme a unidade no desenho.</span>}
          </button></li>)}
        </ul>
      </div>
    </div>
  </div>;
}

function Drawings({ onReport }) {
  const [pdf, setPdf] = useState(null);
  const [cad, setCad] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event, type) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    setBusy(true);
    if (type === "pdf") setPdf(null);
    else setCad(null);
    try {
      const { data } = await api.post(`${base}/${type}`, form);
      if (type === "pdf") { setPdf({ file: form.get("file"), report: data }); onReport?.(data); }
      else setCad(data);
    } catch (e) { setError(errText(e)); }
    finally { setBusy(false); }
  }
  return <div className="grid gap-5">
    <form onSubmit={(event) => submit(event, "pdf")} className="flex flex-wrap items-end gap-3">
      <Field label="PDF vetorial"><input className={input} type="file" name="file" accept=".pdf" required /></Field>
      <button className={button} disabled={busy}>Ler referências</button>
    </form>
    {pdf?.report.estimate_extras && <div className="flex flex-wrap items-center gap-2">
      <button type="button" className={button} disabled={busy} onClick={async () => {
        setBusy(true); setError("");
        try {
          const fd = new FormData(); fd.append("file", pdf.file);
          const { data } = await api.post(`${base}/pdf/model3d`, fd, { responseType: "blob" });
          const url = URL.createObjectURL(data); const a = document.createElement("a");
          a.href = url; a.download = "modelo-clt.ifc"; a.click(); URL.revokeObjectURL(url);
        } catch (e) { setError(errText(e)); } finally { setBusy(false); }
      }}>Descarregar modelo 3D (IFC)</button>
      <span className="text-sm">Paredes, lintéis, laje, coberturas, vigas, vãos e divisões por piso, cada elemento com a folha e a referência de origem.</span>
    </div>}
    {pdf && (pdf.report.pages.length === 4 && pdf.report.pages.every((page) => page.review && page.image)
      ? <CltConfirmation key={pdf.report.sha256} {...pdf} />
      : <Evidence key={pdf.report.sha256} {...pdf} />)}
    <details className="rounded border p-3">
      <summary className="cursor-pointer font-medium">Medir painéis de um DWG ou DXF</summary>
      <form onSubmit={(event) => submit(event, "cad")} className="mt-3 flex flex-wrap items-end gap-3">
        <Field label="Desenho CAD"><input className={input} type="file" name="file" accept=".dwg,.dxf" required /></Field>
        <Field label="Camada dos painéis"><input className={input} name="panel_layer" required /></Field>
        <Field label="Camada dos recortes"><input className={input} name="opening_layer" /></Field>
        <Field label="Espessura confirmada (mm)"><input className={input} type="number" name="thickness_mm" min="0.01" max="1500" step="any" required /></Field>
        <button className={button} disabled={busy}>Medir contornos</button>
      </form>
      {cad && <div className="mt-3 overflow-x-auto">
        <p className="text-sm">Origem: {cad.provider} · Medições para revisão</p>
        <table className="mt-2 w-full text-left text-sm"><thead><tr><th>Painel</th><th>Área líquida</th><th>Volume bruto</th><th>Volume líquido</th></tr></thead>
          <tbody>{cad.panels.map((p) => <tr key={p.handle} className="border-t">
            <td>{p.handle}</td><td>{decimal.format(p.net_area_m2)} m²</td><td>{decimal.format(p.gross_volume_m3)} m³</td><td>{decimal.format(p.net_volume_m3)} m³</td>
          </tr>)}</tbody>
        </table>
      </div>}
    </details>
    {busy && <p role="status">A processar o desenho…</p>}
    {error && <p role="alert" className="text-destructive">{error}</p>}
  </div>;
}

function Rates() {
  const [rates, setRates] = useState([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    api.get(`${base}/rates`).then(({ data }) => setRates(data.items)).catch((e) => setError(errText(e)));
  }, []);
  async function save(event) {
    event.preventDefault();
    const form = event.currentTarget;
    setSaving(true);
    setError("");
    try {
      const { data } = await api.post(`${base}/rates`, Object.fromEntries(new FormData(form)));
      setRates((current) => [data, ...current]);
      form.reset();
    } catch (e) { setError(errText(e)); }
    finally { setSaving(false); }
  }
  return <div className="grid gap-4">
    <form onSubmit={save} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <Field label="Código do artigo"><input className={input} name="code" pattern="[A-Za-z0-9._\-]+" required /></Field>
      <Field label="Designação"><input className={input} name="name" required /></Field>
      <Field label="Tabela"><select className={input} name="kind"><option value="compra">Compra</option><option value="producao">Produção</option><option value="venda">Venda</option></select></Field>
      <Field label="Unidade"><select className={input} name="unit">{units.map((u) => <option key={u}>{u}</option>)}</select></Field>
      <Field label="Valor unitário (€)"><input className={input} name="rate_eur" type="number" min="0" step="0.000001" required /></Field>
      <Field label="Em vigor desde"><input className={input} name="effective_from" type="date" required /></Field>
      <button className={button} disabled={saving}>Guardar nova tarifa</button>
    </form>
    {error && <p role="alert" className="text-destructive">{error}</p>}
    <ul className="divide-y text-sm">{rates.map((r) => <li key={r.rate_id} className="py-2">
      <strong>{r.code} · {r.name}</strong> · {stages[r.kind] || "Venda"} · {fmt(r.rate_eur)}/{r.unit} · {r.effective_from}
    </li>)}</ul>
  </div>;
}

const newLine = () => ({ code: "", name: "", stage: "compra", unit: "m3", rate_eur: "", baseline_qty: "",
  planned_to_date_qty: "0", accepted_qty: "0", actual_eur: "0", open_commitment_eur: "0",
  uncommitted_remaining_eur: "", actual_reference: "", source_reference: "" });
const newLot = () => ({ name: "", revenue_eur: "", planned_delivery: "", forecast_delivery: "", lines: [newLine()] });
const lineFields = [
  ["code", "Código do artigo"], ["name", "Designação"], ["rate_eur", "Custo unitário (€)", true],
  ["baseline_qty", "Quantidade orçamentada", true], ["planned_to_date_qty", "Quantidade prevista até hoje", true],
  ["accepted_qty", "Quantidade aceite", true], ["actual_eur", "Custo real (€)", true],
  ["open_commitment_eur", "Compromisso em aberto (€)", true], ["uncommitted_remaining_eur", "Previsão não contratada (€)", true],
  ["source_reference", "Origem da quantidade"], ["actual_reference", "Referência do custo real"],
];

function Lots() {
  const [items, setItems] = useState([]);
  const [rates, setRates] = useState([]);
  const [draft, setDraft] = useState(newLot);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    api.get(`${base}/lots`).then(({ data }) => setItems(data.items)).catch((e) => setError(errText(e)));
    api.get(`${base}/rates?limit=300`).then(({ data }) => setRates(data.items)).catch((e) => setError(errText(e)));
  }, []);
  function change(key, value) { setDraft((previous) => ({ ...previous, [key]: value })); }
  function changeLine(i, key, value) {
    const clearsRate = ["stage", "unit", "rate_eur"].includes(key);
    setDraft((previous) => ({ ...previous, lines: previous.lines.map((line, n) =>
      n === i ? { ...line, ...(clearsRate ? { rate_id: null } : {}), [key]: value } : line) }));
  }
  function applyRate(i, id) {
    const rate = rates.find((r) => r.rate_id === id);
    setDraft((previous) => ({ ...previous, lines: previous.lines.map((line, n) =>
      n === i ? { ...line, rate_id: rate?.rate_id || null, rate_eur: rate?.rate_eur ?? line.rate_eur } : line) }));
  }
  async function save(event) {
    event.preventDefault();
    const { lot_id, revision, summary, updated_at, updated_by, ...fields } = draft;
    const payload = { ...fields, expected_revision: revision || 0,
      forecast_delivery: fields.forecast_delivery || null,
      lines: fields.lines.map((line) => ({ ...line, uncommitted_remaining_eur: line.uncommitted_remaining_eur === "" ? null : line.uncommitted_remaining_eur })) };
    setSaving(true);
    setError("");
    try {
      const { data } = lot_id ? await api.put(`${base}/lots/${lot_id}`, payload) : await api.post(`${base}/lots`, payload);
      setDraft(data);
      setItems((current) => [data, ...current.filter((x) => x.lot_id !== data.lot_id)]);
    } catch (e) { setError(errText(e)); }
    finally { setSaving(false); }
  }
  return <div className="grid gap-4">
    <div className="flex flex-wrap gap-2">
      <button className={secondary} onClick={() => { setDraft(newLot()); setError(""); }}>Novo lote</button>
      {items.map((item) => <button className={secondary} key={item.lot_id} onClick={() => { setDraft(item); setError(""); }}>{item.name}</button>)}
    </div>
    {draft.summary && <div className="grid gap-2 rounded border p-3 text-sm">
      <strong>Revisão {draft.revision} guardada</strong>
      <span>Real {fmt(draft.summary.actual_eur)} · Desvio {fmt(draft.summary.cost_overrun_to_date_eur)} · Margem prevista {fmt(draft.summary.forecast_margin_eur)}</span>
      <span>Entrega: {draft.summary.delay_days == null ? "por prever" : `${draft.summary.delay_days} dias de desvio`}</span>
      {Object.entries(draft.summary.stages).map(([stage, s]) => <span key={stage}>{stages[stage]} · Aceite {s.accepted_percent ?? "—"}% · Previsto {s.planned_percent ?? "—"}% · Previsão {fmt(s.forecast_cost_eur)}</span>)}
    </div>}
    <form onSubmit={save} className="grid gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Nome do lote"><input className={input} value={draft.name} onChange={(e) => change("name", e.target.value)} required /></Field>
        <Field label="Receita contratada (€)"><input className={input} type="number" min="0" step="0.01" value={draft.revenue_eur} onChange={(e) => change("revenue_eur", e.target.value)} required /></Field>
        <Field label="Entrega contratada"><input className={input} type="date" value={draft.planned_delivery} onChange={(e) => change("planned_delivery", e.target.value)} required /></Field>
        <Field label="Entrega prevista"><input className={input} type="date" value={draft.forecast_delivery || ""} onChange={(e) => change("forecast_delivery", e.target.value)} /></Field>
      </div>
      {draft.lines.map((line, i) => <fieldset key={i} className="grid gap-3 rounded border p-3 sm:grid-cols-2 lg:grid-cols-3">
        <legend className="px-1 font-medium">Artigo {i + 1}</legend>
        <Field label="Fase"><select className={input} value={line.stage} onChange={(e) => changeLine(i, "stage", e.target.value)}>
          {Object.entries(stages).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></Field>
        <Field label="Unidade"><select className={input} value={line.unit} onChange={(e) => changeLine(i, "unit", e.target.value)}>
          {units.map((u) => <option key={u}>{u}</option>)}
        </select></Field>
        <Field label="Tarifa da biblioteca"><select className={input} value={line.rate_id || ""} onChange={(e) => applyRate(i, e.target.value)}>
          <option value="">Introduzir custo unitário</option>
          {line.rate_id && !rates.some((r) => r.rate_id === line.rate_id) && <option value={line.rate_id}>Tarifa guardada</option>}
          {rates.filter((r) => r.unit === line.unit && r.kind === (line.stage === "compra" ? "compra" : "producao"))
            .map((r) => <option key={r.rate_id} value={r.rate_id}>{r.code} · {fmt(r.rate_eur)}/{r.unit} · {r.effective_from}</option>)}
        </select></Field>
        {lineFields.map(([key, label, numeric]) => <Field key={key} label={label}><input className={input}
          type={numeric ? "number" : "text"} min={numeric ? 0 : undefined} step={numeric ? "0.000001" : undefined}
          value={line[key] ?? ""} onChange={(e) => changeLine(i, key, e.target.value)}
          required={!["actual_reference", "uncommitted_remaining_eur"].includes(key)} /></Field>)}
        <button className={secondary} type="button" disabled={draft.lines.length < 2}
          onClick={() => change("lines", draft.lines.filter((_, n) => i !== n))}>Retirar artigo</button>
      </fieldset>)}
      {error && <p role="alert" className="text-destructive">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <button type="button" className={secondary} onClick={() => change("lines", [...draft.lines, newLine()])}>Adicionar artigo</button>
        <button className={button} disabled={saving}>Guardar revisão</button>
      </div>
    </form>
  </div>;
}

const groups = { fabrico: "Fabrico", transporte: "Transporte", montagem: "Montagem em obra", prazos: "Prazos", venda: "Venda e impostos" };
const origins = { empresa: "Empresa", mercado: "Média de mercado", hipotese: "Hipótese por confirmar" };
const stageNames = { compra: "Compra", producao: "Fabrico", transporte: "Transporte", montagem: "Montagem", revestimentos: "Revestimentos e isolamentos", acabamentos: "Instalações e acabamentos", entrega: "Entrega", indiretos: "Engenharia e indiretos", fabrico: "Fabrico" };
const panelKinds = { laje: "Laje", cobertura: "Cobertura", lintel: "Lintel", parede: "Painel sobre vão" };
const EXTRA_FIELDS = [["ceiling_m2", "Teto falso BA15 (m²)"], ["slab_buildup_m2", "Laje: membrana e betão leve (m²)"],
  ["roof_buildup_m2", "Cobertura plana: isolamento e impermeabilização (m²)"], ["facade_m2", "Face exterior das paredes (m²)"], ["steel_beam_m", "Vigas de aço (m)"]];
const newFloor = () => ({ name: "", height_m: "", walls: [{ thickness_mm: "100", layers: "5", length_m: "" }], panels: [], board_layers_m2: "0", paint_m2: "0",
  ceiling_m2: "0", slab_buildup_m2: "0", roof_buildup_m2: "0", facade_m2: "0", steel_beam_m: "0" });
const blankItem = (category) => ({ code: "", category, name: "", unit: "un", cost_eur: "", sale_eur: "", basis: "m3_clt", per_basis: "1", origin: "empresa", source: "", isNew: true });
const TEMPLATE = "Categoria;Código;Designação;Unidade;Custo;Venda;Base;Consumo por base;Fonte\nmateria_prima;MP-LAMELA;Madeira de lamelas C24;m³;315;;m3_madeira;1;Fatura fornecedor\n";

// Faces of a wall run that face another wall (interior), by a ray from the run's middle.
function interiorFaces(run, runs, width, height) {
  const [x, y, X, Y] = run.rect;
  const others = runs.filter((r) => r !== run);
  if ((X - x) * width > (Y - y) * height) {
    const m = (x + X) / 2;
    const hit = (test) => others.some((r) => r.rect[0] <= m && m <= r.rect[2] && test(r.rect));
    return Number(hit((r) => r[3] <= y + 1e-6)) + Number(hit((r) => r[1] >= Y - 1e-6));
  }
  const m = (y + Y) / 2;
  const hit = (test) => others.some((r) => r.rect[1] <= m && m <= r.rect[3] && test(r.rect));
  return Number(hit((r) => r[2] <= x + 1e-6)) + Number(hit((r) => r[0] >= X - 1e-6));
}

export function floorsFromReport(report) {
  if (!report) return null;
  const pages = report.pages.filter((p) => p.review?.in_scope);
  const offsets = report.pages.find((p) => p.review?.structural_offsets)?.review.structural_offsets;
  if (!pages.length || !offsets) return null;
  const keys = ["RDC", "+1"];
  return pages.map((page, i) => {
    const ceilings = page.evidence.filter((e) => e.kind === "ceiling_height").map((e) => e.values[0] / 1000);
    const extra = offsets[keys[i]] || offsets[keys[keys.length - 1]];
    const byThickness = {};
    const runs = page.review.markers.filter((m) => m.length_m);
    runs.forEach((m) => {
      const t = Math.round(m.drawing_width_mm / 10) * 10;
      byThickness[t] = (byThickness[t] || 0) + m.length_m;
    });
    const height = ceilings.length ? Math.max(...ceilings) + extra.floor_buildup_m + extra.ceiling_zone_m : 0;
    const inner = runs.reduce((sum, m) => sum + m.length_m * interiorFaces(m, runs, page.width, page.height), 0);
    const faces = inner * height;
    const outer = (2 * runs.reduce((sum, m) => sum + m.length_m, 0) - inner) * height;
    const more = report.estimate_extras?.floors?.[keys[i]];
    const ceiling = more?.ceiling_m2 || 0;
    // Key of the plans: 100 mm = 5 layers; 80+80 mm = two 3-layer panels (4 glued joints, like 5 layers).
    return { name: keys[i] || page.review.floor, height_m: height ? height.toFixed(3) : "",
      walls: Object.entries(byThickness).map(([t, l]) => ({ thickness_mm: t, layers: "5", length_m: l.toFixed(3) })),
      panels: (more?.panels || []).map((p) => ({ ...p, thickness_mm: String(p.thickness_mm), layers: String(p.layers), area_m2: String(p.area_m2) })),
      board_layers_m2: (2 * faces).toFixed(2), paint_m2: (faces + ceiling).toFixed(2),
      ceiling_m2: ceiling.toFixed(2), slab_buildup_m2: String(more?.slab_buildup_m2 || 0), roof_buildup_m2: String(more?.roof_buildup_m2 || 0),
      facade_m2: outer.toFixed(2), steel_beam_m: String(more?.steel_beam_m || 0),
      rooms: more?.rooms || [], windows: more?.windows || [], interior_doors: more?.interior_doors || 0,
      ceiling_height_m: more?.ceiling_height_m ?? null, riser_m: more?.riser_m || null,
      segments: runs.map((m) => ({ ref: m.id, thickness_mm: String(Math.round(m.drawing_width_mm / 10) * 10), length_m: m.length_m.toFixed(3) })) };
  });
}

function rowsFromText(text) {
  const lines = text.replace(/\r/g, "").split("\n").filter((l) => l.trim());
  const sep = lines[0]?.includes("\t") ? "\t" : lines[0]?.includes(";") ? ";" : ",";
  return lines.map((l) => l.split(sep));
}

function Libraries() {
  const [data, setData] = useState(null);
  const [category, setCategory] = useState("materia_prima");
  const [drafts, setDrafts] = useState({});
  const [paste, setPaste] = useState("");
  const [preview, setPreview] = useState(null);
  const [band, setBand] = useState("MWH500-1999");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const load = () => api.get(`${base}/library`).then(({ data: d }) => setData(d)).catch((e) => setError(errText(e)));
  useEffect(() => { load(); }, []);
  if (!data) return <p role="status">{error || "A carregar as bibliotecas…"}</p>;
  const items = Object.values(data.items).filter((i) => i.category === category);
  const rows = [...items, ...Object.values(drafts).filter((d) => d.isNew && d.category === category)];
  const edit = (code, key, value, item) => setDrafts((all) => ({ ...all, [code]: { ...(all[code] || item), [key]: value } }));
  async function run(action, message) {
    setError(""); setNote("");
    try { const result = await action(); if (result?.items) setData((d) => ({ ...d, items: result.items })); setNote(message); }
    catch (e) { setError(errText(e)); }
  }
  async function save(key, row) {
    const { isNew, standard, deleted, ...item } = row;
    const payload = { ...item, code: item.code.toUpperCase(), sale_eur: item.sale_eur === "" || item.sale_eur == null ? null : item.sale_eur,
      effective_from: item.effective_from || null, origin: "empresa", source: item.source || "Valor da empresa" };
    await run(async () => (await api.put(`${base}/library/${encodeURIComponent(payload.code)}`, payload)).data, `${payload.code} guardado.`);
    setDrafts((all) => { const next = { ...all }; delete next[key]; return next; });
  }
  async function importFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    await run(async () => { const { data: d } = await api.post(`${base}/library/import`, fd); setPreview(d); }, "Pré-visualização pronta. Confirme para guardar.");
    event.target.value = "";
  }
  async function previewPaste() {
    await run(async () => { const { data: d } = await api.post(`${base}/library/table`, { rows: rowsFromText(paste) }); setPreview(d); }, "Pré-visualização pronta. Confirme para guardar.");
  }
  async function confirmPreview() {
    const header = ["code", "name", "unit", "cost", "sale", "base", "por base", "categoria", "fonte"];
    const table = [header, ...preview.items.map((i) => [i.code, i.name, i.unit, i.cost_eur, i.sale_eur ?? "", i.basis, i.per_basis, i.category, i.source])];
    await run(async () => { await api.post(`${base}/library/table`, { rows: table, save: true }); return (await api.get(`${base}/library`)).data; },
      `${preview.items.length} preços guardados.`);
    setPreview(null); setPaste("");
  }
  const cell = "w-full min-w-[6rem] rounded border bg-background px-1.5 py-1 text-sm";
  return <div className="grid gap-4">
    <nav aria-label="Bibliotecas" className="flex flex-wrap gap-2">
      {Object.entries(data.categories).map(([key, label]) => <button key={key} type="button" aria-pressed={category === key}
        className={category === key ? button : secondary} onClick={() => setCategory(key)}>{label}</button>)}
    </nav>
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead><tr><th>Código</th><th>Designação</th><th>Unidade</th><th>Custo (€)</th><th>Venda (€)</th><th>Calculado por</th><th>Quantidade por base</th><th>Origem</th><th /></tr></thead>
        <tbody>{rows.map((item) => {
          const key = item.isNew ? `new-${item._id}` : item.code;
          const row = drafts[key] || item;
          const changed = Boolean(drafts[key]);
          return <tr key={key} className="border-t align-top">
            <td><input className={cell} value={row.code} disabled={!item.isNew} onChange={(e) => edit(key, "code", e.target.value, item)} /></td>
            <td><input className={cell} value={row.name} onChange={(e) => edit(key, "name", e.target.value, item)} /></td>
            <td><input className={cell} value={row.unit} onChange={(e) => edit(key, "unit", e.target.value, item)} /></td>
            <td><input className={cell} type="number" min="0" step="any" value={row.cost_eur} onChange={(e) => edit(key, "cost_eur", e.target.value, item)} /></td>
            <td><input className={cell} type="number" min="0" step="any" value={row.sale_eur ?? ""} onChange={(e) => edit(key, "sale_eur", e.target.value, item)} /></td>
            <td><select className={cell} value={row.basis} onChange={(e) => edit(key, "basis", e.target.value, item)}>
              {Object.entries(data.bases).map(([b, label]) => <option key={b} value={b}>{label}</option>)}</select></td>
            <td><input className={cell} type="number" min="0" step="any" value={row.per_basis} onChange={(e) => edit(key, "per_basis", e.target.value, item)} /></td>
            <td className="max-w-xs text-xs">{changed ? "Empresa · por guardar" : <><strong>{origins[row.origin]}</strong><br />{row.source}</>}</td>
            <td className="flex gap-1">
              <button type="button" className={button} disabled={!changed || !row.code || row.cost_eur === ""} onClick={() => save(key, row)}>Guardar</button>
              {!item.isNew && <button type="button" className={secondary} title={item.standard ? "Retirar do cálculo" : "Apagar"}
                onClick={() => run(async () => (await api.delete(`${base}/library/${encodeURIComponent(item.code)}`)).data, `${item.code} retirado.`)}>Retirar</button>}
            </td>
          </tr>;
        })}</tbody>
      </table>
    </div>
    <div className="flex flex-wrap items-end gap-2">
      <button type="button" className={secondary} onClick={() => { const id = Date.now(); setDrafts((all) => ({ ...all, [`new-${id}`]: { ...blankItem(category), _id: id } })); }}>Adicionar preço</button>
      {category === "energia" && <>
        <Field label="Escalão de consumo anual"><select className={input} value={band} onChange={(e) => setBand(e.target.value)}>
          {["MWH_LT20", "MWH20-499", "MWH500-1999", "MWH2000-19999", "MWH20000-69999", "MWH70000-149999"].map((b) => <option key={b}>{b}</option>)}</select></Field>
        <button type="button" className={button} onClick={() => run(async () => (await api.post(`${base}/library/electricity/refresh?band=${band}`)).data,
          "Preço da eletricidade atualizado a partir do Eurostat.")}>Atualizar eletricidade (Eurostat)</button>
      </>}
    </div>
    <details className="rounded border p-3">
      <summary className="cursor-pointer font-medium">Colar do Excel ou importar ficheiro (Excel, CSV, PDF)</summary>
      <div className="mt-3 grid gap-3">
        <p className="text-sm">Colunas: Categoria, Código, Designação, Unidade, Custo, Venda, Base, Consumo por base, Fonte. Copie as linhas no Excel com o cabeçalho e cole aqui. <a className="underline" download="modelo-precos-clt.csv" href={`data:text/csv;charset=utf-8,${encodeURIComponent(TEMPLATE)}`}>Descarregar modelo</a></p>
        <textarea className={`${input} min-h-32 font-mono`} value={paste} onChange={(e) => setPaste(e.target.value)} placeholder="Cole aqui as células do Excel" />
        <div className="flex flex-wrap gap-2">
          <button type="button" className={secondary} disabled={!paste.trim()} onClick={previewPaste}>Pré-visualizar</button>
          <label className={secondary}>Importar ficheiro<input type="file" className="sr-only" accept=".xlsx,.xlsm,.csv,.tsv,.pdf" onChange={importFile} /></label>
        </div>
        {preview && <div className="grid gap-2 text-sm">
          <p>{preview.items.length} preços reconhecidos{preview.errors.length ? ` · ${preview.errors.length} linhas com erro` : ""}.</p>
          <ul className="list-disc pl-5">{preview.items.slice(0, 50).map((i) => <li key={i.code}>{i.code} · {i.name} · {fmt(Number(i.cost_eur))}/{i.unit} · {data.bases[i.basis]}</li>)}</ul>
          {preview.errors.map((e) => <p key={e.row} className="text-destructive">Linha {e.row}: {e.error}</p>)}
          <button type="button" className={button} disabled={!preview.items.length} onClick={confirmPreview}>Guardar estes preços</button>
        </div>}
      </div>
    </details>
    {note && <p role="status" className="text-sm">{note}</p>}
    {error && <p role="alert" className="text-destructive">{error}</p>}
  </div>;
}

function TechnicalParameters() {
  const [items, setItems] = useState(null);
  const [edits, setEdits] = useState({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    api.get(`${base}/parameters`).then(({ data }) => setItems(data.items)).catch((e) => setError(errText(e)));
  }, []);
  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const saved = Object.fromEntries(Object.entries(items).filter(([, item]) => item.origin === "empresa")
        .map(([key, item]) => [key, { value: item.value, origin: "empresa", source: item.source }]));
      const payload = { ...saved, ...Object.fromEntries(Object.entries(edits).map(([key, value]) => [key, { value, origin: "empresa", source: "Valor da empresa" }])) };
      const { data } = await api.put(`${base}/parameters`, payload);
      setItems(data.items);
      setEdits({});
    } catch (e) { setError(errText(e)); }
    finally { setSaving(false); }
  }
  if (!items) return <p role="status">{error || "A carregar os parâmetros…"}</p>;
  return <form onSubmit={save} className="grid gap-4">
    {Object.entries(groups).map(([group, title]) => <fieldset key={group} className="grid gap-3 rounded border p-3 sm:grid-cols-2 lg:grid-cols-3">
      <legend className="px-1 font-medium">{title}</legend>
      {Object.entries(items).filter(([, item]) => item.group === group).map(([key, item]) => <Field key={key} label={`${item.label} (${item.unit})`}>
        <input className={input} type="number" min="0" step="any" value={edits[key] ?? item.value}
          onChange={(e) => setEdits((current) => ({ ...current, [key]: e.target.value }))} required />
        <span className="text-xs text-muted-foreground">{key in edits ? "Empresa · por guardar" : `${origins[item.origin]} · ${item.source}`}</span>
      </Field>)}
    </fieldset>)}
    <button className={button} disabled={saving}>Guardar parâmetros técnicos</button>
    {error && <p role="alert" className="text-destructive">{error}</p>}
  </form>;
}

function Gantt({ plan }) {
  const start = new Date(plan.inicio).getTime();
  const span = Math.max(1, (new Date(plan.fim).getTime() - start) / 86400000 + 1);
  return <div className="grid gap-1 text-sm">
    {plan.fases.map((s) => {
      const left = ((new Date(s.inicio).getTime() - start) / 86400000) / span * 100;
      const width = Math.max(2, (s.dias || 1) / span * 100);
      return <div key={s.fase} className="grid grid-cols-[10rem_1fr] items-center gap-2">
        <span>{stageNames[s.fase]} · {s.dias} d</span>
        <div className="relative h-6 rounded bg-muted">
          <div className="absolute h-6 rounded bg-primary" style={{ left: `${left}%`, width: `${width}%` }} title={`${s.inicio} → ${s.fim}`} />
        </div>
      </div>;
    })}
    <p>Início {plan.inicio} · entrega montada {plan.fim} · {plan.dias} dias</p>
  </div>;
}

function Calculation({ report }) {
  const fromPdf = floorsFromReport(report);
  const [floors, setFloors] = useState(fromPdf || [newFloor()]);
  const [start, setStart] = useState(new Date().toISOString().slice(0, 10));
  const [mode, setMode] = useState("compra");
  const [result, setResult] = useState(null);
  const [lot, setLot] = useState(null);
  const [error, setError] = useState("");
  const body = () => ({ floors, start, start_mode: mode });
  async function calculate(event) {
    event?.preventDefault();
    setError(""); setLot(null);
    try { setResult((await api.post(`${base}/estimate`, body())).data); } catch (e) { setError(errText(e)); }
  }
  async function createLot() {
    setError("");
    try { setLot((await api.post(`${base}/estimate/lot`, { ...body(), lot_name: `Cálculo ${start}` })).data.lot); } catch (e) { setError(errText(e)); }
  }
  const setFloor = (i, key, value) => setFloors((all) => all.map((f, n) => n === i ? { ...f, [key]: value } : f));
  const setWall = (i, w, key, value) => setFloors((all) => all.map((f, n) => n === i ? { ...f, walls: f.walls.map((x, m) => m === w ? { ...x, [key]: value } : x) } : f));
  const setPanel = (i, w, key, value) => setFloors((all) => all.map((f, n) => n === i ? { ...f, panels: (f.panels || []).map((x, m) => m === w ? { ...x, [key]: value } : x) } : f));
  return <form onSubmit={calculate} className="grid gap-3">
    {fromPdf && <p className="text-sm">Pisos preenchidos a partir do último PDF lido: paredes medidas, altura estrutural do corte, laje, cobertura, lintéis, painéis sobre portas, teto BA15, vigas de aço e revestimentos (BA13 duplo e pintura nas faces interiores, como no corte). Confirme antes de orçamentar.</p>}
    {report?.estimate_extras?.notes?.length > 0 && <ul className="list-disc pl-5 text-sm">{report.estimate_extras.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
    <div className="flex flex-wrap gap-3">
      <Field label="Data de início"><input className={input} type="date" value={start} onChange={(e) => setStart(e.target.value)} required /></Field>
      <Field label="Começar o plano em"><select className={input} value={mode} onChange={(e) => setMode(e.target.value)}>
        <option value="compra">Compra da matéria-prima</option><option value="fabrico">Início do fabrico</option></select></Field>
    </div>
    {floors.map((floor, i) => <fieldset key={i} className="grid gap-3 rounded border p-3 sm:grid-cols-2 lg:grid-cols-4">
      <legend className="px-1">Piso {i + 1}</legend>
      <Field label="Nome"><input className={input} value={floor.name} onChange={(e) => setFloor(i, "name", e.target.value)} required /></Field>
      <Field label="Altura estrutural (m)"><input className={input} type="number" min="0.01" step="any" value={floor.height_m} onChange={(e) => setFloor(i, "height_m", e.target.value)} required /></Field>
      <Field label="Placa de gesso (m², somando camadas)"><input className={input} type="number" min="0" step="any" value={floor.board_layers_m2} onChange={(e) => setFloor(i, "board_layers_m2", e.target.value)} /></Field>
      <Field label="Pintura (m²)"><input className={input} type="number" min="0" step="any" value={floor.paint_m2} onChange={(e) => setFloor(i, "paint_m2", e.target.value)} /></Field>
      {floor.walls.map((wall, w) => <div key={w} className="grid gap-3 sm:col-span-2 lg:col-span-4 sm:grid-cols-3">
        <Field label="Espessura (mm)"><input className={input} type="number" min="1" step="any" value={wall.thickness_mm} onChange={(e) => setWall(i, w, "thickness_mm", e.target.value)} required /></Field>
        <Field label="Camadas (juntas coladas + 1)"><input className={input} type="number" min="3" max="9" step="1" value={wall.layers} onChange={(e) => setWall(i, w, "layers", e.target.value)} required /></Field>
        <Field label="Comprimento medido (m)"><input className={input} type="number" min="0.01" step="any" value={wall.length_m} onChange={(e) => setWall(i, w, "length_m", e.target.value)} required /></Field>
      </div>)}
      <button type="button" className={secondary} onClick={() => setFloor(i, "walls", [...floor.walls, { thickness_mm: "100", layers: "5", length_m: "" }])}>Adicionar espessura</button>
      {(floor.panels || []).map((panel, w) => <div key={`p${w}`} className="grid gap-3 sm:col-span-2 lg:col-span-4 sm:grid-cols-5">
        <Field label="Elemento CLT"><select className={input} value={panel.kind} onChange={(e) => setPanel(i, w, "kind", e.target.value)}>
          {Object.entries(panelKinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label="Descrição"><input className={input} value={panel.label || ""} onChange={(e) => setPanel(i, w, "label", e.target.value)} /></Field>
        <Field label="Espessura (mm)"><input className={input} type="number" min="1" step="any" value={panel.thickness_mm} onChange={(e) => setPanel(i, w, "thickness_mm", e.target.value)} required /></Field>
        <Field label="Camadas"><input className={input} type="number" min="3" max="13" step="1" value={panel.layers} onChange={(e) => setPanel(i, w, "layers", e.target.value)} required /></Field>
        <Field label="Área (m²)"><span className="flex gap-1"><input className={input} type="number" min="0.001" step="any" value={panel.area_m2} onChange={(e) => setPanel(i, w, "area_m2", e.target.value)} required />
          <button type="button" className={secondary} aria-label="Retirar elemento" onClick={() => setFloor(i, "panels", floor.panels.filter((_, m) => m !== w))}>×</button></span></Field>
      </div>)}
      <button type="button" className={secondary} onClick={() => setFloor(i, "panels", [...(floor.panels || []), { kind: "laje", label: "", thickness_mm: "240", layers: "7", area_m2: "" }])}>Adicionar laje, cobertura ou lintel</button>
      {(floor.rooms?.length > 0 || floor.windows?.length > 0) && <details className="sm:col-span-2 lg:col-span-4">
        <summary className="cursor-pointer">Divisões, aparelhos e vãos lidos no desenho ({floor.rooms.length} divisões, {floor.windows.length} vãos exteriores, {floor.interior_doors} portas interiores)</summary>
        <table className="mt-2 w-full text-left text-sm"><thead><tr><th>Divisão</th><th>Tipo</th><th>Área</th><th>Aparelhos</th><th>Lados a confirmar</th></tr></thead>
          <tbody>{floor.rooms.map((r) => <tr key={r.nome} className="border-t"><td>{r.nome}</td><td>{r.tipo}</td><td>{decimal.format(r.area_m2)} m²</td>
            <td>{(r.aparelhos || []).join(", ") || "—"}</td><td>{(r.lados_a_confirmar || []).join(", ") || "—"}</td></tr>)}</tbody></table>
        <p className="mt-2">Vãos exteriores: {floor.windows.map((w) => `${decimal.format(w.largura_m)} m${w.sobre ? ` sob ${w.sobre}` : ""}`).join(" · ")}</p>
      </details>}
      {EXTRA_FIELDS.map(([key, label]) => <Field key={key} label={label}><input className={input} type="number" min="0" step="any" value={floor[key] ?? "0"} onChange={(e) => setFloor(i, key, e.target.value)} /></Field>)}
    </fieldset>)}
    <div className="flex flex-wrap gap-2">
      <button type="button" className={secondary} onClick={() => setFloors((all) => [...all, newFloor()])}>Adicionar piso</button>
      <button className={button}>Calcular custo total</button>
    </div>
    {result && <div className="grid gap-4 text-sm">
      <div className="grid gap-2 sm:grid-cols-5">
        {[["Custo total", fmt(result.total.custo_total_eur)], ["Venda", fmt(result.total.receita_eur)],
          ["Margem", `${fmt(result.total.margem_eur)}${result.total.margem_percent != null ? ` · ${result.total.margem_percent}%` : ""}`],
          ["Prazo", `${result.plano.dias} dias`], [`Venda com IVA ${result.total.iva_percent}%`, fmt(result.total.receita_com_iva_eur)]].map(([label, value]) => <div key={label} className="rounded border p-3"><span className="block text-muted-foreground">{label}</span><strong className="text-lg">{value}</strong></div>)}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left"><thead><tr><th>Piso</th><th>m² montagem</th><th>m³ fabrico</th><th>h fabrico</th><th>h montagem</th>
          {Object.keys(result.total.custos_eur).map((s) => <th key={s}>{stageNames[s]}</th>)}<th>Custo</th><th>Venda</th><th>Margem</th></tr></thead>
          <tbody>{[...result.pisos, { piso: "Total", ...result.total }].map((row) => <tr key={row.piso} className="border-t">
            <th>{row.piso}</th><td>{decimal.format(row.montagem_m2)}</td><td>{decimal.format(row.fabrico_m3)}</td><td>{decimal.format(row.horas_fabrico)}</td>
            <td>{decimal.format(row.horas_montagem)}</td>
            {Object.keys(result.total.custos_eur).map((s) => <td key={s}>{fmt(row.custos_eur[s])}</td>)}
            <td>{fmt(row.custo_total_eur)}</td><td>{fmt(row.receita_eur)}</td>
            <td>{fmt(row.margem_eur)}{row.margem_percent != null ? ` · ${row.margem_percent}%` : ""}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <Gantt plan={result.plano} />
      <details><summary className="cursor-pointer">Detalhe por preço da biblioteca</summary>
        <table className="mt-2 w-full text-left"><thead><tr><th>Código</th><th>Designação</th><th>Quantidade</th><th>Custo</th><th>Venda</th><th>Origem</th></tr></thead>
          <tbody>{result.linhas.map((l) => <tr key={l.codigo} className="border-t"><td>{l.codigo}</td><td>{l.designacao}</td>
            <td>{decimal.format(l.quantidade)} {l.unidade}</td><td>{fmt(l.custo_eur)}</td><td>{l.venda_eur == null ? "—" : fmt(l.venda_eur)}</td><td>{origins[l.origem]}</td></tr>)}</tbody>
        </table>
      </details>
      {result.notas_quantidades?.length > 0 && <ul className="list-disc pl-5">{result.notas_quantidades.map((n) => <li key={n}>{n}</li>)}</ul>}
      {result.hipoteses_por_confirmar.length > 0 && <p className="text-amber-700 dark:text-amber-400">Estimativa com {result.hipoteses_por_confirmar.length} valores por confirmar: {result.hipoteses_por_confirmar.join(" · ")}.</p>}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={button} onClick={createLot}>Criar lote de seguimento com este plano</button>
        {lot && <span>Lote "{lot.name}" criado. O avanço segue-se no separador Custos e avanço.</span>}
      </div>
    </div>}
    {error && <p role="alert" className="text-destructive">{error}</p>}
  </form>;
}

function CostWorkspace({ report }) {
  const [section, setSection] = useState("calculo");
  return <div className="grid gap-4">
    <nav aria-label="Custos CLT" className="flex flex-wrap gap-2">
      {Object.entries({ calculo: "1 · Cálculo total, plano e margem", bibliotecas: "2 · Bibliotecas de preços", parametros: "3 · Parâmetros técnicos" }).map(([key, label]) =>
        <button key={key} type="button" aria-pressed={section === key} className={section === key ? button : secondary} onClick={() => setSection(key)}>{label}</button>)}
    </nav>
    {section === "calculo" ? <Calculation report={report} /> : section === "bibliotecas" ? <Libraries /> : <TechnicalParameters />}
  </div>;
}

export default function CltIndustrial() {
  const [available, setAvailable] = useState(null);
  const [tab, setTab] = useState("desenhos");
  const [report, setReport] = useState(null);
  useEffect(() => {
    api.get(`${base}/config`).then(() => setAvailable(true)).catch(() => setAvailable(false));
  }, []);
  if (available === null) return <p className="p-4" role="status">A verificar o acesso…</p>;
  if (!available) return <p className="p-4">O piloto CLT está indisponível nesta conta.</p>;
  return <main className="mx-auto grid max-w-7xl gap-5 p-4">
    <h1 className="text-2xl font-semibold">ConstruPilot CLT</h1>
    <nav aria-label="Piloto CLT" className="flex flex-wrap gap-2">
      {Object.entries({ desenhos: "Desenhos e medições", parametros: "Custos, preços e plano", lotes: "Seguimento e avanço", precos: "Tarifas dos lotes" }).map(([key, label]) =>
        <button key={key} type="button" aria-pressed={tab === key} className={tab === key ? button : secondary} onClick={() => setTab(key)}>{label}</button>)}
    </nav>
    <div hidden={tab !== "desenhos"}><Drawings onReport={setReport} /></div>
    {tab === "parametros" ? <CostWorkspace key={report?.sha256 || "manual"} report={report} /> : tab === "precos" ? <Rates /> : tab === "lotes" ? <Lots /> : null}
  </main>;
}
