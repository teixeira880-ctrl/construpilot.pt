import { useState } from "react";
import { api } from "@/lib/api";

const base = "/clt-industrial/motores";
const input = "w-full rounded border bg-background px-2 py-1.5 text-sm";
const button = "rounded bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50";
const secondary = "rounded border px-3 py-2 text-sm disabled:opacity-50";
const num = new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 3 });
const errText = (e) => typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Verifique o ficheiro e os valores.";

function Field({ label, children }) {
  return <label className="grid gap-1 text-sm"><span>{label}</span>{children}</label>;
}

function Check({ ok, label }) {
  return <li className={ok ? "text-green-700 dark:text-green-400" : "text-destructive"}>{ok ? "✓" : "✗"} {label}</li>;
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

export default function CltEngines() {
  const [floors, setFloors] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [variableWidth, setVariableWidth] = useState(false);

  async function read(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = form.get("floor_name");
    const elevation = Number(form.get("elevation_m") || 0);
    form.delete("floor_name");
    form.delete("elevation_m");
    if (!form.get("scale")) form.delete("scale");
    // Plan without heights: company standard, RDC 3,00 m and the other floors 2,50 m.
    const standard = !form.get("height_m");
    if (standard) form.set("height_m", floors.filter((f) => f.name !== name).length ? "2.5" : "3");
    setBusy("read"); setError("");
    try {
      const { data } = await api.post(`${base}/pdf-paredes`, form);
      setFloors((prev) => [...prev.filter((f) => f.name !== name),
        { name, elevation_m: elevation, walls: data.paredes, scale: data.origem_escala,
          standardHeight: standard, pending: data.tracejados_por_confirmar.length, rejected: data.rejeitados.length, analysis: data.analise }]);
      setResult(null);
    } catch (e) { setError(errText(e)); } finally { setBusy(""); }
  }

  const body = () => ({ name: "ConstruPilot CLT", floors: floors.map(({ name, elevation_m, walls }) => ({ name, elevation_m, walls })),
    cutting: { variable_width: variableWidth } });

  async function analyse() {
    setBusy("analyse"); setError("");
    try { setResult((await api.post(`${base}/analise`, body())).data); } catch (e) { setError(errText(e)); } finally { setBusy(""); }
  }

  async function file(kind) {
    setBusy(kind); setError("");
    try {
      if (kind === "ifc") await download(`${base}/ifc`, body(), "construpilot-clt.ifc");
      else await download(`${base}/desenhos?formato=${kind}`, body(), `construpilot-clt-fabrico.${kind}`);
    } catch (e) { setError(e?.response?.status === 422 ? "O modelo não passou a verificação de volumes." : errText(e)); } finally { setBusy(""); }
  }

  return <section className="grid gap-4">
    <p className="text-sm text-muted-foreground">Leitura automática das paredes CLT num PDF vetorial, juntas sem contagem dupla, plano de corte nos painéis de prensa (18 × 3,5 m Rezult), modelo 3D IFC verificado e desenhos de fabrico. Tudo o que é lido fica "detetado, por confirmar" até conferência.</p>
    <form onSubmit={read} className="grid gap-3 rounded border p-3 md:grid-cols-4">
      <Field label="Planta em PDF vetorial"><input className={input} type="file" name="file" accept="application/pdf" required /></Field>
      <Field label="Piso"><input className={input} name="floor_name" defaultValue={floors.length ? "+1" : "RDC"} required maxLength={60} /></Field>
      <Field label="Cota da base das paredes (m)"><input className={input} name="elevation_m" type="number" step="0.001" min="-50" max="500" defaultValue={floors.length ? "3.384" : "0"} /></Field>
      <Field label="Página"><input className={input} name="page" type="number" min="1" max="60" defaultValue="2" required /></Field>
      <Field label="Altura estrutural das paredes (m)"><input className={input} name="height_m" type="number" step="0.001" min="0.5" max="3.5" placeholder={floors.length ? "standard 2,50" : "standard 3,00"} /></Field>
      <Field label="Escala 1: (vazio = ler na folha)"><input className={input} name="scale" type="number" min="10" max="500" placeholder="50" /></Field>
      <Field label="Camadas"><input className={input} name="layers" type="number" min="3" max="13" defaultValue="5" /></Field>
      <div className="flex items-end"><button className={button} disabled={!!busy}>{busy === "read" ? "A ler…" : "Ler paredes do PDF"}</button></div>
    </form>
    {floors.length > 0 && <div className="overflow-x-auto rounded border p-3 text-sm">
      <table className="w-full text-left"><thead><tr><th>Piso</th><th>Paredes</th><th>Comprimento (m)</th><th>Volume bruto (m³)</th><th>Juntas</th><th>Escala</th><th>Por confirmar</th><th /></tr></thead>
        <tbody>{floors.map((f) => <tr key={f.name} className="border-t">
          <td>{f.name}{f.standardHeight && <span className="block text-xs text-muted-foreground">altura standard</span>}</td><td>{f.walls.length}</td><td>{num.format(f.analysis?.metodos.pecas_producao_m || 0)}</td>
          <td>{num.format(f.analysis?.totais.volume_bruto_m3 || 0)}</td><td>{f.analysis?.juntas.length || 0}</td><td>{f.scale}</td>
          <td>{f.pending} tracejados · {f.rejected} rejeitados</td>
          <td><button type="button" className={secondary} onClick={() => setFloors(floors.filter((x) => x.name !== f.name))}>Retirar</button></td>
        </tr>)}</tbody>
      </table>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2"><input type="checkbox" checked={variableWidth} onChange={(e) => setVariableWidth(e.target.checked)} /> Painel produzido à largura pedida</label>
        <button type="button" className={button} disabled={!!busy} onClick={analyse}>{busy === "analyse" ? "A calcular…" : "Calcular juntas, corte e 3D"}</button>
        <button type="button" className={secondary} disabled={!!busy} onClick={() => file("ifc")}>Modelo IFC</button>
        <button type="button" className={secondary} disabled={!!busy} onClick={() => file("pdf")}>Desenhos PDF</button>
        <button type="button" className={secondary} disabled={!!busy} onClick={() => file("dxf")}>Desenhos DXF</button>
      </div>
    </div>}
    {result && <div className="grid gap-2 rounded border p-3 text-sm">
      <ul>
        <Check ok={result.verificacoes.pecas_vs_planta} label="Volume das peças = união das plantas (GEOS)" />
        <Check ok={result.verificacoes.ifc_opencascade} label={`Volume 3D OpenCascade = analítico (${num.format(result.verificacao_3d.volume_ifc_m3)} m³)`} />
      </ul>
      <p>Volume líquido {num.format(result.total.volume_liquido_m3)} m³ · painéis de prensa {result.total.paineis} ({num.format(result.total.volume_paineis_m3)} m³) · desperdício {num.format(result.total.desperdicio_percent)} % · juntas verticais {num.format(result.total.juntas_parede_m)} m · contagem dupla evitada {num.format(result.total.contagem_dupla_evitada_m3)} m³</p>
      {result.corte.grupos.map((g) => <details key={`${g.espessura_mm}-${g.camadas}`}><summary>CLT {g.espessura_mm} mm {g.camadas}c · {g.paineis} painéis (mínimo teórico {g.limite_inferior_paineis}) · {g.motor}</summary>
        <ul className="list-disc pl-5">{g.layout.map((b) => <li key={b.painel}>Painel {b.painel}: {num.format(b.comprimento_usado_m)} × {num.format(b.largura_m)} m · {b.pecas.map((p) => p.id).join(", ")} · aproveitamento {b.aproveitamento_percent} %</li>)}</ul>
      </details>)}
      <p className="text-muted-foreground">Formato: {result.corte.parametros.origem_formato}. Corte de serra: {result.corte.parametros.origem_corte}.</p>
    </div>}
    {error && <p role="alert" className="text-destructive">{error}</p>}
  </section>;
}
