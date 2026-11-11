import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const base = "/clt-industrial";
const input = "w-full rounded border bg-background px-2 py-1.5 text-sm";
const button = "rounded bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50";
const secondary = "rounded border px-3 py-2 text-sm";
const units = ["m3", "m2", "m", "kg", "h", "un", "viagem", "lote", "L"];
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
        {report.pages.map((p) => <option key={p.page} value={p.page}>{p.page} de {report.pages.length}</option>)}
      </select></Field>
    </div>
    <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(250px,2fr)]">
      {url ? <div className="relative self-start overflow-hidden rounded border">
        <img src={url} alt={`Folha ${number} do desenho`} className="block w-full" />
        {mark && <span aria-hidden="true" className="absolute border-2 border-amber-500 bg-amber-400/25" style={{
          left: `${mark.rect[0] * 100}%`, top: `${mark.rect[1] * 100}%`,
          width: `${(mark.rect[2] - mark.rect[0]) * 100}%`, height: `${(mark.rect[3] - mark.rect[1]) * 100}%`,
        }} />}
      </div> : <p role="status">{error || "A carregar a folha…"}</p>}
      <div>
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

function Drawings() {
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
      if (type === "pdf") setPdf({ file: form.get("file"), report: data });
      else setCad(data);
    } catch (e) { setError(errText(e)); }
    finally { setBusy(false); }
  }
  return <div className="grid gap-5">
    <form onSubmit={(event) => submit(event, "pdf")} className="flex flex-wrap items-end gap-3">
      <Field label="PDF vetorial"><input className={input} type="file" name="file" accept=".pdf" required /></Field>
      <button className={button} disabled={busy}>Ler referências</button>
    </form>
    {pdf && <Evidence key={pdf.report.sha256} {...pdf} />}
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

export default function CltIndustrial() {
  const [available, setAvailable] = useState(null);
  const [tab, setTab] = useState("desenhos");
  useEffect(() => {
    api.get(`${base}/config`).then(() => setAvailable(true)).catch(() => setAvailable(false));
  }, []);
  if (available === null) return <p className="p-4" role="status">A verificar o acesso…</p>;
  if (!available) return <p className="p-4">O piloto CLT está indisponível nesta conta.</p>;
  return <main className="mx-auto grid max-w-7xl gap-5 p-4">
    <h1 className="text-2xl font-semibold">ConstruPilot CLT</h1>
    <nav aria-label="Piloto CLT" className="flex flex-wrap gap-2">
      {Object.entries({ desenhos: "Desenhos e medições", precos: "Biblioteca da empresa", lotes: "Custos e avanço" }).map(([key, label]) =>
        <button key={key} type="button" aria-pressed={tab === key} className={tab === key ? button : secondary} onClick={() => setTab(key)}>{label}</button>)}
    </nav>
    {tab === "desenhos" ? <Drawings /> : tab === "precos" ? <Rates /> : <Lots />}
  </main>;
}
