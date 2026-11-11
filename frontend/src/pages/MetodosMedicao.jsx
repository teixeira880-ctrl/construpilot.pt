import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

// Common take-off methods (CLT and traditional construction), the same for every company:
// plan already read in "Plantas e medições" (or a project file) → study with the origin of each number →
// cross-checks → estimate with price sources → premium dossier with the dimensioned drawings attached.
const base = "/metodos";
const input = "w-full rounded border bg-background px-2 py-1.5 text-sm";
const button = "rounded bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50";
const secondary = "rounded border px-3 py-2 text-sm disabled:opacity-50";
const num = new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 2 });
const errText = (e) => typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Verifique os dados e tente de novo.";
const ORIGIN = {
  medido: ["medido", "bg-green-100 text-green-900 dark:bg-green-900/40 dark:text-green-100"],
  regra: ["regra", "bg-blue-100 text-blue-900 dark:bg-blue-900/40 dark:text-blue-100"],
  estimativa: ["estimativa", "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-100"],
  estimativa_imagem: ["estimativa de imagem", "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-100"],
};
const LABELS = {
  parede_comprimento: "Paredes, comprimento", parede_area_bruta: "Paredes, área bruta", parede_area_vaos: "Paredes, área dos vãos",
  parede_area_liquida: "Paredes, área líquida", parede_volume: "Paredes, volume", clt_pecas: "Peças CLT", clt_volume: "Painéis CLT, volume",
  alvenaria_area: "Alvenaria", alvenaria_unidades: "Tijolos/blocos", alvenaria_argamassa: "Argamassa", lintel_comprimento: "Lintéis",
  reboco_area: "Reboco/estuque", betao_volume: "Betão", cofragem_area: "Cofragem", aco_massa: "Aço (taxa)", montantes_un: "Montantes",
  montantes_comprimento: "Montantes, comprimento", travessas_comprimento: "Guias, padieiras e peitoris", placas_area: "Placas",
  isolamento_parede_area: "Isolamento de parede", vaos_janela: "Janelas", vaos_porta: "Portas", vaos_vao: "Vãos (sob lintel)",
  pavimento_area: "Pavimento", teto_area: "Teto", rodape_comprimento: "Rodapé",
};

function Badge({ origin }) {
  const [label, cls] = ORIGIN[origin] || [origin, "bg-muted"];
  return <span className={`rounded px-1.5 py-0.5 text-xs ${cls}`}>{label}</span>;
}

async function download(path, body, filename) {
  const { data } = await api.post(path, body, { responseType: "blob" });
  const url = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function MetodosMedicao() {
  const [catalogue, setCatalogue] = useState(null);
  const [plans, setPlans] = useState([]);
  const [planId, setPlanId] = useState("");
  const [pages, setPages] = useState([]);
  const [meta, setMeta] = useState({ nome: "Estudo", pais: "PT", sistema: "alvenaria_tijolo", lang: "pt" });
  const [project, setProject] = useState(null);
  const [notes, setNotes] = useState([]);
  const [result, setResult] = useState(null);
  const [edits, setEdits] = useState({});
  const [libraryText, setLibraryText] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  async function load() {
    const [{ data: cat }, { data: pl }] = await Promise.all([api.get(`${base}/sistemas`), api.get(`${base}/plantas`)]);
    setCatalogue(cat);
    setPlans(pl.plantas || []);
    setLibraryText((cat.biblioteca || []).map((i) => [i.codigo, i.sistema || "", i.preco_unitario, i.unidade, i.fonte].join(";")).join("\n"));
  }
  useEffect(() => { load().catch((e) => setError(errText(e))); }, []);

  const plan = useMemo(() => plans.find((p) => p.plan_id === planId), [plans, planId]);
  useEffect(() => {
    if (!plan) return setPages([]);
    setPages((plan.pages || []).map((pg, i) => ({
      index: pg.index ?? i, use: i === 0, nome: pg.level_label || (i === 0 ? "RDC" : `Piso ${i}`), nivel: pg.level_index ?? i, altura_m: "",
    })));
  }, [plan]);

  async function run(label, fn) {
    setBusy(label); setError(""); setSaved("");
    try { await fn(); } catch (e) { setError(errText(e)); } finally { setBusy(""); }
  }

  const fromPlan = () => run("planta", async () => {
    const chosen = pages.filter((p) => p.use).map((p) => ({ index: p.index, nome: p.nome, nivel: Number(p.nivel) || 0,
      altura_m: p.altura_m ? Number(p.altura_m) : null }));
    const { data } = await api.post(`${base}/plantas/${planId}/projeto`, { nome: meta.nome, pais: meta.pais, sistema: meta.sistema, paginas: chosen });
    setProject(data.projeto); setNotes(data.notas || []); setResult(null);
  });

  async function fromFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      setProject({ ...data, nome: data.nome || meta.nome }); setNotes([]); setResult(null); setError("");
    } catch { setError("O ficheiro não é um projeto JSON válido."); }
  }

  const body = () => ({ ...project, nome: meta.nome, pais: meta.pais, sistema: meta.sistema });
  const calculate = () => run("estudo", async () => setResult((await api.post(`${base}/estudo`, body())).data));
  const saveParams = () => run("parametros", async () => {
    const valores = {};
    Object.entries(catalogue.parametros).forEach(([k, v]) => { if (v.origem === "empresa") valores[k] = v.valor; });
    Object.entries(edits).forEach(([k, v]) => { if (v !== "") valores[k] = Number(v); });
    await api.put(`${base}/parametros`, { valores });
    setEdits({}); await load(); setSaved("Parâmetros guardados.");
  });
  const saveLibrary = () => run("biblioteca", async () => {
    const itens = libraryText.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
      const [codigo, sistema, preco, unidade, ...fonte] = l.split(";");
      return { codigo: codigo.trim(), sistema: sistema.trim() || null, preco_unitario: Number(String(preco).replace(",", ".")),
        unidade: (unidade || "").trim(), fonte: fonte.join(";").trim() };
    });
    await api.put(`${base}/biblioteca`, { itens });
    await load(); setSaved(`${itens.length} preços guardados.`);
  });

  if (!catalogue) return <div className="p-6 text-sm">{error || "A carregar…"}</div>;
  const systems = Object.entries(catalogue.sistemas);
  const groups = {};
  Object.entries(catalogue.parametros).forEach(([k, v]) => { (groups[k.split(".")[0]] ||= []).push([k, v]); });

  return (
    <div className="mx-auto grid max-w-6xl gap-6 p-4">
      <header>
        <h1 className="text-2xl font-semibold">Medições, orçamento e dossier: métodos comuns</h1>
        <p className="text-sm text-muted-foreground">
          Os mesmos métodos do motor CLT para todas as construções e todas as empresas: alturas da planta (sem alturas, RDC 3,00 m e
          outros pisos 2,50 m, marcadas «standard»), juntas sem contagem dupla, cada número com a sua origem, verificação por dois
          métodos e dossier com os desenhos cotados em anexo.
        </p>
      </header>

      <section className="grid gap-3 rounded border p-4">
        <h2 className="font-semibold">1. Projeto</h2>
        <div className="grid gap-3 md:grid-cols-4">
          <label className="grid gap-1 text-sm">Nome<input className={input} value={meta.nome} onChange={(e) => setMeta({ ...meta, nome: e.target.value })} /></label>
          <label className="grid gap-1 text-sm">Sistema construtivo
            <select className={input} value={meta.sistema} onChange={(e) => setMeta({ ...meta, sistema: e.target.value })}>
              {systems.map(([k, v]) => <option key={k} value={k}>{v.nome}</option>)}
            </select></label>
          <label className="grid gap-1 text-sm">País (IVA)
            <select className={input} value={meta.pais} onChange={(e) => setMeta({ ...meta, pais: e.target.value })}>
              <option value="PT">Portugal</option><option value="FR">França</option><option value="UA">Ucrânia</option>
            </select></label>
          <label className="grid gap-1 text-sm">Língua do dossier
            <select className={input} value={meta.lang} onChange={(e) => setMeta({ ...meta, lang: e.target.value })}>
              <option value="pt">Português</option><option value="en">English</option><option value="uk">Українська</option><option value="fr">Français</option>
            </select></label>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          <label className="grid gap-1 text-sm">Planta já lida em «Plantas e medições»
            <select className={input} value={planId} onChange={(e) => setPlanId(e.target.value)}>
              <option value="">Escolher…</option>
              {plans.map((p) => <option key={p.plan_id} value={p.plan_id}>{p.filename || p.plan_id} ({p.page_count || p.pages?.length || 0} pág.)</option>)}
            </select></label>
          <label className="grid gap-1 text-sm">Ou um projeto (JSON com pisos e paredes por eixo)
            <input type="file" accept="application/json,.json" className={input} onChange={fromFile} /></label>
        </div>
        {pages.length > 0 && (
          <table className="text-sm">
            <thead><tr className="text-left"><th>Usar</th><th>Página</th><th>Piso</th><th>Nível (0 = RDC)</th><th>Altura do corte (vazio = standard)</th></tr></thead>
            <tbody>{pages.map((p, i) => (
              <tr key={p.index}>
                <td><input type="checkbox" checked={p.use} onChange={(e) => setPages(pages.map((q, j) => j === i ? { ...q, use: e.target.checked } : q))} /></td>
                <td>{p.index + 1}</td>
                <td><input className={input} value={p.nome} onChange={(e) => setPages(pages.map((q, j) => j === i ? { ...q, nome: e.target.value } : q))} /></td>
                <td><input className={input} type="number" value={p.nivel} onChange={(e) => setPages(pages.map((q, j) => j === i ? { ...q, nivel: e.target.value } : q))} /></td>
                <td><input className={input} type="number" step="0.01" value={p.altura_m} onChange={(e) => setPages(pages.map((q, j) => j === i ? { ...q, altura_m: e.target.value } : q))} /></td>
              </tr>))}</tbody>
          </table>)}
        <div className="flex flex-wrap gap-2">
          <button className={secondary} disabled={!planId || busy} onClick={fromPlan}>{busy === "planta" ? "A ler…" : "Ler as paredes da planta"}</button>
          <button className={button} disabled={!project || busy} onClick={calculate}>{busy === "estudo" ? "A calcular…" : "Calcular"}</button>
          <button className={secondary} disabled={!project || busy} onClick={() => run("dossier", () => download(`${base}/dossier?lang=${meta.lang}`, body(), `${meta.nome} - dossier.pdf`))}>Dossier PDF</button>
          <button className={secondary} disabled={!project || busy} onClick={() => run("pdf", () => download(`${base}/desenhos?formato=pdf&lang=${meta.lang}`, body(), `${meta.nome} - desenhos cotados.pdf`))}>Desenhos cotados PDF</button>
          <button className={secondary} disabled={!project || busy} onClick={() => run("dxf", () => download(`${base}/desenhos?formato=dxf&lang=${meta.lang}`, body(), `${meta.nome} - desenhos cotados.dxf`))}>DXF</button>
        </div>
        {project && <p className="text-sm text-muted-foreground">{project.pisos?.length} piso(s), {project.pisos?.reduce((n, f) => n + f.paredes.length, 0)} paredes lidas.</p>}
        {notes.length > 0 && <ul className="list-disc pl-5 text-sm text-amber-700 dark:text-amber-300">{notes.map((n) => <li key={n}>{n}</li>)}</ul>}
        {error && <p className="text-sm text-destructive">{error}</p>}
        {saved && <p className="text-sm text-green-700 dark:text-green-400">{saved}</p>}
      </section>

      {result && (
        <section className="grid gap-3 rounded border p-4">
          <h2 className="font-semibold">2. Resultado</h2>
          <p className={result.verificacoes_ok ? "text-sm text-green-700 dark:text-green-400" : "text-sm text-destructive"}>
            {result.verificacoes_ok ? "✓ Verificações cruzadas dentro da tolerância" : "✗ Há verificações fora da tolerância"}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left"><th>Designação</th><th>Sistema</th><th className="text-right">Quantidade</th><th>Un.</th><th>Origem</th></tr></thead>
              <tbody>{result.totais.map((r) => (
                <tr key={`${r.codigo}-${r.sistema}`} className="border-t">
                  <td>{LABELS[r.codigo] || r.codigo}</td><td>{r.sistema ? catalogue.sistemas[r.sistema]?.nome : "—"}</td>
                  <td className="text-right">{num.format(r.quantidade)}</td><td>{r.unidade}</td><td><Badge origin={r.origem} /></td>
                </tr>))}</tbody>
            </table>
          </div>
          <ul className="text-sm">{result.verificacoes.map((c) => (
            <li key={`${c.piso}-${c.verificacao}`}>{c.informativo ? "ℹ" : c.passou ? "✓" : "✗"} {c.piso} · {c.verificacao}: {num.format(c.a)} / {num.format(c.b)} {c.unidade}{c.erro_pct != null ? ` (${num.format(c.erro_pct)} %)` : ""}</li>))}</ul>
          {result.orcamento && <p className="text-sm">Total sem IVA {num.format(result.orcamento.subtotal)} € · IVA {num.format(result.orcamento.iva_pct)} % · total {num.format(result.orcamento.total)} € · {result.orcamento.sem_preco.length} quantidades sem preço</p>}
        </section>)}

      <section className="grid gap-3 rounded border p-4">
        <h2 className="font-semibold">3. Parâmetros da empresa</h2>
        <p className="text-sm text-muted-foreground">Cada valor tem a sua origem. Um valor alterado pela empresa deixa de ser hipótese e passa a «regra».</p>
        {Object.entries(groups).map(([g, items]) => (
          <details key={g} className="rounded border p-2">
            <summary className="cursor-pointer text-sm font-medium">{g === "geral" ? "Geometria e verificações" : catalogue.sistemas[g]?.nome || g}</summary>
            <table className="mt-2 w-full text-sm"><tbody>{items.map(([k, v]) => (
              <tr key={k} className="border-t">
                <td className="py-1">{k.split(".")[1]}</td>
                <td className="w-32"><input className={input} type="number" step="any" placeholder={String(v.valor)} value={edits[k] ?? ""} onChange={(e) => setEdits({ ...edits, [k]: e.target.value })} /></td>
                <td className="w-16">{v.unidade}</td><td className="w-24"><Badge origin={v.origem === "empresa" || v.origem === "fabricante" ? "regra" : "estimativa"} /></td>
                <td className="text-xs text-muted-foreground">{v.fonte}</td>
              </tr>))}</tbody></table>
          </details>))}
        <div><button className={button} disabled={busy} onClick={saveParams}>Guardar parâmetros</button></div>
      </section>

      <section className="grid gap-3 rounded border p-4">
        <h2 className="font-semibold">4. Biblioteca de preços</h2>
        <p className="text-sm text-muted-foreground">Uma linha por preço: código;sistema (opcional);preço unitário;unidade;fonte. Ex.: <code>alvenaria_area;alvenaria_tijolo;28,50;m²;Tabela fornecedor 2026</code></p>
        <textarea className={`${input} h-40 font-mono`} value={libraryText} onChange={(e) => setLibraryText(e.target.value)} />
        <div><button className={button} disabled={busy} onClick={saveLibrary}>Guardar biblioteca</button></div>
      </section>
    </div>
  );
}
