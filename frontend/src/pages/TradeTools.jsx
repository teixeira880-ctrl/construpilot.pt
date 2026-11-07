import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Calculator, Loader2, Plus, Trash2, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, eur2 } from "@/lib/api";
import { fmt, term, useWorkProfile } from "@/lib/workProfile";

// Ferramentas por ofício. O cálculo é feito no servidor (engines/trade_calcs.py),
// o mesmo motor usado pelo orçamento guiado: resultados idênticos em todos os modos.
const TOOLS = {
  paint: { title: "Tinta", intro: "Litros e latas de tinta a partir das medidas das divisões, do número de demãos e do rendimento do produto." },
  floor: { title: "Pavimento / revestimento", intro: "Número de embalagens a partir da área, das perdas e da cobertura de cada embalagem." },
  masonry: { title: "Alvenaria", intro: "Número de blocos ou tijolos para uma parede. Só quantidades: não verifica estabilidade." },
  points: { title: "Pontos (água / eletricidade)", intro: "Levantamento dos pontos e equipamentos por divisão, com totais para o orçamento. Não dimensiona instalações." },
  carpentry: { title: "Carpintaria", intro: "Lista de peças → área de placa por material, orla e ferragens." },
};
const POINT_TYPES = {
  canalizacao: [["agua_fria", "Ponto de água fria"], ["agua_quente", "Ponto de água quente"], ["esgoto", "Ponto de esgoto"], ["sanita", "Sanita"], ["lavatorio", "Lavatório"], ["base_duche", "Base de duche / banheira"], ["lava_loica", "Lava-loiça"], ["maquina", "Máquina (lavar roupa / loiça)"], ["esquentador", "Esquentador / termoacumulador"], ["outro", "Outro"]],
  eletricidade: [["tomada", "Tomada"], ["tomada_dedicada", "Tomada dedicada (forno, placa, máquina)"], ["interruptor", "Interruptor / comutador"], ["ponto_luz", "Ponto de luz"], ["tomada_rede", "Tomada de rede / TV"], ["quadro", "Quadro elétrico"], ["campainha", "Campainha / intercomunicador"], ["outro", "Outro"]],
};

const Field = ({ label, unit, value, onChange, hint, testid }) => (
  <label className="block text-sm font-medium">{label}
    <div className="mt-1 flex items-center gap-2">
      <input type="number" inputMode="decimal" min="0" step="any" value={value ?? ""} onChange={e => onChange(e.target.value)} data-testid={testid}
        className="h-11 w-full min-w-0 rounded-xl border bg-background px-3" />{unit && <span className="shrink-0 text-xs text-muted-foreground">{unit}</span>}
    </div>{hint && <span className="mt-1 block text-xs font-normal text-muted-foreground">{hint}</span>}
  </label>
);

export default function TradeTools() {
  const [params, setParams] = useSearchParams();
  const tool = TOOLS[params.get("ferramenta")] ? params.get("ferramenta") : "paint";
  const { profile } = useWorkProfile();
  const lang = profile.language || "simples";
  const advanced = profile.mode === "avancado";
  const guided = profile.mode === "guiado";
  const [inputs, setInputs] = useState({
    paint: { rooms: [{ name: "Divisão 1", length_m: "", width_m: "", height_m: "", openings: [] }], coats: "", yield_m2_per_l: "", can_size_l: "" },
    floor: { length_m: "", width_m: "", area_m2: "", waste_pct: "", package_m2: "", piece_length_m: "", piece_width_m: "", pieces_per_package: "", package_price: "" },
    masonry: { wall_length_m: "", wall_height_m: "", block_length_m: "", block_height_m: "", joint_m: "", waste_pct: "", openings: [] },
    points: { trade: "eletricidade", items: [{ room: "", type: "tomada", qty: "", label: "" }], prices: {} },
    carpentry: { pieces: [{ name: "", material: "", length_m: "", width_m: "", qty: "1", edges_m: "", hardware: [] }], waste_pct: "", sheet_m2: "" },
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const data = inputs[tool];
  const set = (patch) => setInputs(s => ({ ...s, [tool]: { ...s[tool], ...patch } }));
  const blank = v => (v === "" ? null : v);

  const compute = async () => {
    setBusy(true); setError("");
    const payload = JSON.parse(JSON.stringify(data, (k, v) => (v === "" ? null : v)));
    try { const { data: r } = await api.post(`/trade-tools/${tool}/compute`, payload); setResult(r); }
    catch (e) { setResult(null); setError(e?.response?.data?.detail || "Não foi possível calcular."); }
    finally { setBusy(false); }
  };

  const hint = (text) => (guided || advanced ? text : undefined);
  const openings = (list, onChange) => <div className="space-y-2 sm:col-span-2">
    <p className="text-sm font-medium">{term("openings", lang)}</p>
    {list.map((o, k) => <div key={k} className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
      <Field label="Largura" unit="m" value={o.width_m} onChange={v => onChange(list.map((x, j) => j === k ? { ...x, width_m: v } : x))} />
      <Field label="Altura" unit="m" value={o.height_m} onChange={v => onChange(list.map((x, j) => j === k ? { ...x, height_m: v } : x))} />
      <Button variant="ghost" size="icon" aria-label="Remover" onClick={() => onChange(list.filter((_, j) => j !== k))}><Trash2 className="h-4 w-4" /></Button></div>)}
    <Button type="button" variant="outline" size="sm" onClick={() => onChange([...list, { width_m: "", height_m: "" }])}><Plus className="mr-1 h-4 w-4" />Abertura</Button>
  </div>;

  return (
    <div className="mx-auto max-w-3xl space-y-4 pb-16" data-testid="trade-tools">
      <div><p className="text-xs font-semibold uppercase tracking-wide text-primary">Ferramentas de ofício</p><h1 className="text-2xl font-bold">{TOOLS[tool].title}</h1>
        <p className="text-sm text-muted-foreground">{TOOLS[tool].intro}</p></div>
      <div className="flex flex-wrap gap-2" role="tablist">
        {Object.entries(TOOLS).map(([k, t]) => <button key={k} role="tab" aria-selected={k === tool} type="button" data-testid={`tool-tab-${k}`}
          onClick={() => { setParams({ ferramenta: k }); setResult(null); setError(""); }}
          className={`min-h-10 rounded-xl border px-3 text-sm ${k === tool ? "border-primary bg-primary/10 font-semibold" : ""}`}>{t.title}</button>)}
      </div>

      <div className="grid gap-4 rounded-2xl border bg-card p-4 sm:grid-cols-2 sm:p-6">
        {tool === "paint" && <>
          {data.rooms.map((r, i) => <fieldset key={i} className="grid gap-3 rounded-xl border p-3 sm:col-span-2 sm:grid-cols-4">
            <label className="block text-sm font-medium sm:col-span-4">Nome<input className="mt-1 h-11 w-full rounded-xl border bg-background px-3" value={r.name} onChange={e => set({ rooms: data.rooms.map((x, j) => j === i ? { ...x, name: e.target.value } : x) })} /></label>
            {[["length_m", "Comprimento"], ["width_m", "Largura"], ["height_m", term("ceiling_height", lang)]].map(([k, l]) =>
              <Field key={k} label={l} unit="m" value={r[k]} testid={`paint-${i}-${k}`} onChange={v => set({ rooms: data.rooms.map((x, j) => j === i ? { ...x, [k]: v } : x) })} />)}
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!r.paint_ceiling} onChange={e => set({ rooms: data.rooms.map((x, j) => j === i ? { ...x, paint_ceiling: e.target.checked } : x) })} />Incluir teto</label>
            {openings(r.openings, ops => set({ rooms: data.rooms.map((x, j) => j === i ? { ...x, openings: ops } : x) }))}
            {data.rooms.length > 1 && <Button variant="ghost" size="sm" className="justify-self-start" onClick={() => set({ rooms: data.rooms.filter((_, j) => j !== i) })}><Trash2 className="mr-1 h-4 w-4" />Remover divisão</Button>}
          </fieldset>)}
          <Button type="button" variant="outline" className="sm:col-span-2" onClick={() => set({ rooms: [...data.rooms, { name: `Divisão ${data.rooms.length + 1}`, length_m: "", width_m: "", height_m: "", openings: [] }] })}><Plus className="mr-1 h-4 w-4" />Divisão</Button>
          <Field label={term("coats", lang)} value={data.coats} onChange={v => set({ coats: v })} testid="paint-coats" hint={hint("Normalmente 2. Veja a ficha técnica.")} />
          <Field label={term("yield", lang)} unit="m²/L" value={data.yield_m2_per_l} onChange={v => set({ yield_m2_per_l: v })} testid="paint-yield" hint={hint("Indicado no rótulo ou na ficha técnica do produto.")} />
          <Field label="Tamanho da lata" unit="L" value={data.can_size_l} onChange={v => set({ can_size_l: v })} testid="paint-can" />
        </>}
        {tool === "floor" && <>
          <Field label="Comprimento" unit="m" value={data.length_m} onChange={v => set({ length_m: v })} testid="floor-length" />
          <Field label="Largura" unit="m" value={data.width_m} onChange={v => set({ width_m: v })} testid="floor-width" />
          {advanced && <Field label="Ou área total" unit="m²" value={data.area_m2} onChange={v => set({ area_m2: v })} />}
          <Field label={term("waste", lang)} unit="%" value={data.waste_pct} onChange={v => set({ waste_pct: v })} testid="floor-waste" hint={hint("Colocação reta 5–10 %; diagonal 12–15 %.")} />
          <Field label="m² por embalagem" unit="m²" value={data.package_m2} onChange={v => set({ package_m2: v })} testid="floor-package" hint={hint("Vem escrito na caixa. Se não souber, preencha as dimensões da peça abaixo.")} />
          {(advanced || !blank(data.package_m2)) && <>
            <Field label="Comprimento da peça" unit="m" value={data.piece_length_m} onChange={v => set({ piece_length_m: v })} />
            <Field label="Largura da peça" unit="m" value={data.piece_width_m} onChange={v => set({ piece_width_m: v })} />
            <Field label="Peças por embalagem" value={data.pieces_per_package} onChange={v => set({ pieces_per_package: v })} /></>}
          <Field label="Preço por embalagem (opcional)" unit="€" value={data.package_price} onChange={v => set({ package_price: v })} />
        </>}
        {tool === "masonry" && <>
          <Field label="Comprimento da parede" unit="m" value={data.wall_length_m} onChange={v => set({ wall_length_m: v })} testid="mas-length" />
          <Field label="Altura da parede" unit="m" value={data.wall_height_m} onChange={v => set({ wall_height_m: v })} testid="mas-height" />
          <Field label="Comprimento do bloco" unit="m" value={data.block_length_m} onChange={v => set({ block_length_m: v })} hint={hint("Ex.: tijolo 30×20 → 0,30")} />
          <Field label="Altura do bloco" unit="m" value={data.block_height_m} onChange={v => set({ block_height_m: v })} hint={hint("Ex.: 0,20")} />
          <Field label="Espessura da junta" unit="m" value={data.joint_m} onChange={v => set({ joint_m: v })} hint={hint("Ex.: 0,01 (1 cm)")} />
          <Field label={term("waste", lang)} unit="%" value={data.waste_pct} onChange={v => set({ waste_pct: v })} />
          {openings(data.openings, ops => set({ openings: ops }))}
        </>}
        {tool === "points" && <>
          <div className="flex gap-2 sm:col-span-2">{[["eletricidade", "Eletricidade"], ["canalizacao", "Canalização"]].map(([k, l]) =>
            <button key={k} type="button" onClick={() => set({ trade: k, items: [{ room: "", type: POINT_TYPES[k][0][0], qty: "", label: "" }] })} data-testid={`points-trade-${k}`}
              className={`min-h-10 rounded-xl border px-3 text-sm ${data.trade === k ? "border-primary bg-primary/10 font-semibold" : ""}`}>{l}</button>)}</div>
          {data.items.map((it, i) => <div key={i} className="grid grid-cols-2 gap-2 rounded-xl border p-2 sm:col-span-2 sm:grid-cols-[1fr_2fr_80px_auto]">
            <input aria-label="Divisão" className="h-11 rounded-lg border bg-background px-2" placeholder="Divisão" value={it.room} onChange={e => set({ items: data.items.map((x, j) => j === i ? { ...x, room: e.target.value } : x) })} />
            <select aria-label="Tipo" className="h-11 rounded-lg border bg-background px-2" value={it.type} onChange={e => set({ items: data.items.map((x, j) => j === i ? { ...x, type: e.target.value } : x) })} data-testid={`points-${i}-type`}>
              {POINT_TYPES[data.trade].map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
            <input aria-label="Quantidade" type="number" min="0" inputMode="numeric" className="h-11 rounded-lg border bg-background px-2" placeholder="Qtd." value={it.qty} onChange={e => set({ items: data.items.map((x, j) => j === i ? { ...x, qty: e.target.value } : x) })} data-testid={`points-${i}-qty`} />
            <Button variant="ghost" size="icon" aria-label="Remover" onClick={() => set({ items: data.items.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></Button>
            {it.type === "outro" && <input aria-label="Descrição" className="col-span-2 h-11 rounded-lg border bg-background px-2 sm:col-span-4" placeholder="Descreva" value={it.label} onChange={e => set({ items: data.items.map((x, j) => j === i ? { ...x, label: e.target.value } : x) })} />}
          </div>)}
          <Button type="button" variant="outline" className="sm:col-span-2" onClick={() => set({ items: [...data.items, { room: data.items.at(-1)?.room || "", type: POINT_TYPES[data.trade][0][0], qty: "", label: "" }] })} data-testid="points-add"><Plus className="mr-1 h-4 w-4" />Ponto</Button>
        </>}
        {tool === "carpentry" && <>
          {data.pieces.map((p, i) => <fieldset key={i} className="grid grid-cols-2 gap-2 rounded-xl border p-3 sm:col-span-2 sm:grid-cols-3">
            <label className="text-sm font-medium">Peça<input className="mt-1 h-11 w-full rounded-xl border bg-background px-3" placeholder="Lateral" value={p.name} onChange={e => set({ pieces: data.pieces.map((x, j) => j === i ? { ...x, name: e.target.value } : x) })} /></label>
            <label className="text-sm font-medium">Material<input className="mt-1 h-11 w-full rounded-xl border bg-background px-3" placeholder="MDF 19 mm" value={p.material} onChange={e => set({ pieces: data.pieces.map((x, j) => j === i ? { ...x, material: e.target.value } : x) })} data-testid={`carp-${i}-material`} /></label>
            {[["length_m", "Comprimento", "m"], ["width_m", "Largura", "m"], ["qty", "Quantidade", ""], ["edges_m", "Orla por peça", "m"]].map(([k, l, u]) =>
              <Field key={k} label={l} unit={u} value={p[k]} testid={`carp-${i}-${k}`} onChange={v => set({ pieces: data.pieces.map((x, j) => j === i ? { ...x, [k]: v } : x) })} />)}
            <div className="col-span-2 space-y-1 sm:col-span-3"><p className="text-sm font-medium">Ferragens por peça</p>
              {p.hardware.map((h, k) => <div key={k} className="grid grid-cols-[2fr_1fr_auto] gap-2">
                <input className="h-10 rounded-lg border bg-background px-2" placeholder="Dobradiça" value={h.name} onChange={e => set({ pieces: data.pieces.map((x, j) => j === i ? { ...x, hardware: x.hardware.map((y, z) => z === k ? { ...y, name: e.target.value } : y) } : x) })} />
                <input type="number" min="0" className="h-10 rounded-lg border bg-background px-2" placeholder="Qtd." value={h.qty} onChange={e => set({ pieces: data.pieces.map((x, j) => j === i ? { ...x, hardware: x.hardware.map((y, z) => z === k ? { ...y, qty: e.target.value } : y) } : x) })} />
                <Button variant="ghost" size="icon" aria-label="Remover" onClick={() => set({ pieces: data.pieces.map((x, j) => j === i ? { ...x, hardware: x.hardware.filter((_, z) => z !== k) } : x) })}><Trash2 className="h-4 w-4" /></Button></div>)}
              <Button variant="outline" size="sm" onClick={() => set({ pieces: data.pieces.map((x, j) => j === i ? { ...x, hardware: [...x.hardware, { name: "", qty: "" }] } : x) })}><Plus className="mr-1 h-4 w-4" />Ferragem</Button></div>
            {data.pieces.length > 1 && <Button variant="ghost" size="sm" className="justify-self-start" onClick={() => set({ pieces: data.pieces.filter((_, j) => j !== i) })}><Trash2 className="mr-1 h-4 w-4" />Remover peça</Button>}
          </fieldset>)}
          <Button type="button" variant="outline" className="sm:col-span-2" onClick={() => set({ pieces: [...data.pieces, { name: "", material: data.pieces.at(-1)?.material || "", length_m: "", width_m: "", qty: "1", edges_m: "", hardware: [] }] })}><Plus className="mr-1 h-4 w-4" />Peça</Button>
          <Field label={term("waste", lang)} unit="%" value={data.waste_pct} onChange={v => set({ waste_pct: v })} testid="carp-waste" hint={hint("Perdas de corte; 10–20 % é habitual.")} />
          <Field label="Área de uma placa" unit="m²" value={data.sheet_m2} onChange={v => set({ sheet_m2: v })} testid="carp-sheet" hint={hint("Ex.: placa 2,75 × 1,84 m = 5,06 m²")} />
        </>}
        <Button type="button" className="min-h-12 sm:col-span-2" onClick={compute} disabled={busy} data-testid="tool-compute">{busy ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Calculator className="mr-1 h-4 w-4" />}Calcular</Button>
        {error && <p className="text-sm text-red-600 sm:col-span-2" role="alert" data-testid="tool-error">{error}</p>}
      </div>

      {result && <section className="space-y-2 rounded-2xl border border-primary/30 bg-card p-4 sm:p-6" data-testid="tool-result" aria-live="polite">
        <h2 className="text-lg font-semibold">Resultado</h2>
        {tool === "paint" && <>
          <p>Superfície: <strong>{fmt(result.surface_m2)} m²</strong></p>
          <p>Tinta: <strong data-testid="paint-liters">{result.liters != null ? `${fmt(result.liters, 1)} L` : "—"}</strong>{result.cans != null && <> → <strong>{result.cans} lata(s)</strong></>}</p>
          {advanced && <ul className="text-xs text-muted-foreground">{result.rooms.map((r, i) => <li key={i}>{r.name}: {fmt(r.walls_gross_m2)} − {fmt(r.openings_m2)} = {fmt(r.walls_net_m2)} m²{r.ceiling_m2 ? ` + teto ${fmt(r.ceiling_m2)}` : ""}</li>)}</ul>}
        </>}
        {tool === "floor" && <>
          <p>Área com perdas: <strong>{fmt(result.area_with_waste_m2)} m²</strong></p>
          <p>Embalagens: <strong data-testid="floor-packages">{result.packages ?? "—"}</strong>{result.material_cost != null && <> · custo {eur2(result.material_cost)}</>}</p>
        </>}
        {tool === "masonry" && <>
          <p>Área líquida: <strong>{fmt(result.net_area_m2)} m²</strong> · {fmt(result.blocks_per_m2)} blocos/m²</p>
          <p>Blocos: <strong data-testid="mas-blocks">{result.blocks ?? "—"}</strong></p>
          <p className="text-xs text-muted-foreground">{result.limits}</p>
        </>}
        {tool === "points" && <>
          <ul className="text-sm" data-testid="points-totals">{Object.entries(result.totals).map(([k, v]) => <li key={k}><strong>{fmt(v, 0)}</strong> × {k}</li>)}</ul>
          {advanced && <ul className="text-xs text-muted-foreground">{Object.entries(result.by_room).map(([room, t]) => <li key={room}>{room}: {Object.entries(t).map(([k, v]) => `${fmt(v, 0)} ${k}`).join(", ")}</li>)}</ul>}
          <p className="text-xs text-muted-foreground">{result.limits}</p>
        </>}
        {tool === "carpentry" && <>
          <ul className="text-sm" data-testid="carp-materials">{result.materials.map(m => <li key={m.material}>{m.material}: {fmt(m.area_m2)} m² → com perdas {fmt(m.area_with_waste_m2)} m²{m.sheets != null && <> → <strong>{m.sheets} placa(s)</strong></>}</li>)}</ul>
          <p>Orla: <strong>{fmt(result.edge_banding_ml)} ml</strong></p>
          {Object.keys(result.hardware).length > 0 && <p>Ferragens: {Object.entries(result.hardware).map(([k, v]) => `${fmt(v, 0)} × ${k}`).join(", ")}</p>}
          <p className="text-xs text-muted-foreground">{result.limits}</p>
        </>}
        {result.formula && <p className="text-xs text-muted-foreground">Fórmula: {result.formula}</p>}
        {result.pending?.length > 0 && <div className="rounded-xl bg-amber-500/10 p-3 text-sm" data-testid="tool-pending"><p className="flex items-center gap-1 font-semibold"><TriangleAlert className="h-4 w-4" />Falta indicar</p>
          <ul className="list-disc pl-5">{result.pending.map(p => <li key={p}>{p}</li>)}</ul>
          {Object.values(result.suggestions || {}).map(s => <p key={s.note} className="mt-1 text-xs">Sugestão (a confirmar): {s.value} — {s.note}</p>)}</div>}
        {tool === "paint" && <Link to="/orcamento-guiado" className="inline-block text-sm font-semibold text-primary underline">Preparar o orçamento de pintura passo a passo →</Link>}
      </section>}
    </div>
  );
}
