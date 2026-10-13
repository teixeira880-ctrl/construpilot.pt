import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { FileDown, Layers, Loader2, Plus, Trash2 } from "lucide-react";

const inputClass = "w-full min-w-0 border rounded p-2 bg-white text-sm";
const empty = () => ({ basis: "design_draft", placements: [], openings: [], cuts: [], bars: [], notes: [] });
const nextId = (prefix, rows, key = "id") => { let n = 1; while (rows.some(r => r[key] === `${prefix}${n}`)) n++; return `${prefix}${n}`; };
function NumberField({ label, value, onChange, step = "any" }) {
  return <label className="block text-xs min-w-0">{label}<Input aria-label={label} className="mt-1" type="number" step={step} value={value ?? ""} onChange={e => onChange(e.target.value === "" ? null : Number(e.target.value))} /></label>;
}
function TextField({ label, value, onChange, maxLength = 600 }) {
  return <label className="block text-xs min-w-0">{label}<Input aria-label={label} className="mt-1" value={value || ""} maxLength={maxLength} onChange={e => onChange(e.target.value)} /></label>;
}
function ElementSelect({ model, value, change, label }) {
  return <label className="block text-xs min-w-0">{label}<select aria-label={label} className={`${inputClass} mt-1`} value={value} onChange={e => change(e.target.value)}><option value="">Escolher um elemento</option>{model.elements.map(e => <option key={e.id} value={e.id}>{`${e.id} · ${e.level}`}</option>)}</select></label>;
}
function Delete({ label, click }) { return <Button type="button" variant="ghost" size="sm" aria-label={label} onClick={click}><Trash2 className="h-4 w-4" /></Button>; }
function PointFields({ point, label, change }) {
  return <div className="grid grid-cols-3 gap-2">{["x", "y", "z"].map(k => <NumberField key={k} label={`${label} ${k.toUpperCase()} (m)`} value={point[k]} onChange={v => change({ ...point, [k]: v })} />)}</div>;
}

export default function StructureDrawingsPanel({ study, model, change, dirty, download }) {
  const d = model.drawings;
  const [manifest, setManifest] = useState(null), [error, setError] = useState(""), [loading, setLoading] = useState(false);
  const [sheet, setSheet] = useState(""), [preview, setPreview] = useState(""), [previewError, setPreviewError] = useState("");
  const sourceStale = !!study.source_stale;
  const ready = !!d && !dirty && !sourceStale;
  const base = `/structuro/calc/studies/${study.study_id}`;
  useEffect(() => {
    let active = true;
    setManifest(null); setError(""); setLoading(false);
    if (!ready) return () => { active = false; };
    setLoading(true);
    api.get(`${base}/drawings`, { params: { expected_revision: study.revision } }).then(({ data }) => {
      if (active) { setManifest(data); setSheet(previous => data.sheets.some(s => s.id === previous) ? previous : data.sheets[0]?.id || ""); }
    }).catch(e => { if (active) setError(e?.response?.status === 409 ? "Esta revisão mudou. Recarregue o estudo." : "Controlo do processo indisponível. Tente novamente reabrindo o estudo."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [base, study.revision, ready]);
  useEffect(() => {
    let active = true, url = "";
    setPreview(""); setPreviewError("");
    if (!ready || !manifest?.can_export || !sheet) return () => { active = false; };
    api.get(`${base}/drawings/${sheet}`, { params: { expected_revision: study.revision }, responseType: "blob" }).then(({ data }) => {
      if (active) { url = URL.createObjectURL(data); setPreview(url); }
    }).catch(e => { if (active) setPreviewError(e?.response?.status === 409 ? "Folha ultrapassada. Recarregue o estudo." : "Não foi possível carregar a pré-visualização."); });
    return () => { active = false; if (url) URL.revokeObjectURL(url); };
  }, [base, study.revision, ready, manifest, sheet]);
  const set = (key, value) => change({ ...d, [key]: value });
  const update = (key, i, row) => set(key, d[key].map((r, j) => i === j ? row : r));
  const remove = (key, i) => set(key, d[key].filter((_, j) => i !== j));
  const editPlacement = (id, patch) => {
    const found = d.placements.find(p => p.element_id === id);
    set("placements", found ? d.placements.map(p => p.element_id === id ? { ...p, ...patch, generated_by: null } : p) : [...d.placements, { element_id: id, base_z_m: null, source: "", ...patch }]);
  };
  const addBar = () => set("bars", [...d.bars, { mark: nextId("A", d.bars, "mark"), element_id: "", diameter_mm: null, count: 1, points: [{ x: null, y: null, z: null }, { x: null, y: null, z: null }], repeat: { x: 0, y: 0, z: 0 }, bend_radius_mm: 0, cover_mm: null, source: "", role: "" }]);
  return <Card className="p-4 md:p-6 space-y-5 min-w-0" data-testid="structure-drawings">
    <div className="flex flex-wrap justify-between gap-3"><div><p className="text-xs uppercase tracking-widest text-emerald-800">Oficina de plantas · A3</p><h2 className="text-xl font-semibold flex items-center gap-2 mt-1"><Layers className="h-5 w-5" />Cofragem, cortes e armaduras</h2></div>{d && <span className="text-xs rounded-full border px-3 py-2 self-start">{d.basis === "demonstration" ? "Exemplo fictício" : "Processo de trabalho"} · não executório</span>}</div>
    <p className="text-sm text-muted-foreground">As folhas e a lista utilizam os mesmos elementos e traçados. Complete o processo, guarde o estudo e depois consulte os controlos e a pré-visualização antes de transferir.</p>
    {!d ? <Button variant="outline" onClick={() => change(empty())}>Preparar o processo de plantas</Button> : <>
      <div className="grid md:grid-cols-4 gap-2 text-xs">{["1 · Elementos e cotas", "2 · Negativos e cortes", "3 · Traçados dos aços", "4 · Controlos e PDF"].map(t => <div key={t} className="bg-emerald-50 rounded px-3 py-2 text-emerald-950">{t}</div>)}</div>
      <details className="border rounded-lg p-4" open={!d.placements.length}>
        <summary className="font-medium cursor-pointer">Implantação e cotas · {d.placements.length}/{model.elements.length} elementos</summary>
        <p className="text-xs text-muted-foreground my-3">A origem X/Y, a rotação e as dimensões são as do modelo estrutural. Indique aqui a cota da face inferior de cada elemento, em metros em relação ao mesmo zero.</p>
        {!model.elements.length && <p className="text-sm">Adicione os elementos estruturais ao modelo para começar.</p>}
        <div className="space-y-4">{model.elements.map(e => {
          const p = d.placements.find(p => p.element_id === e.id);
          return <div key={e.id} className="grid sm:grid-cols-[1fr_170px_2fr] gap-3 border-b pb-3"><div className="text-sm self-center"><b>{e.id}</b> · {e.level}<p className="text-xs text-muted-foreground">{[e.length_m, e.width_m, e.height_m].map(n => n ?? "?").join(" × ")} m</p></div><NumberField label={`Base ${e.id} (m)`} value={p?.base_z_m} onChange={v => editPlacement(e.id, { base_z_m: v })} /><TextField label={`Fonte da cota ${e.id}`} value={p?.source} onChange={v => editPlacement(e.id, { source: v })} /></div>;
        })}</div>
        {d.placements.some(p => !model.elements.some(e => e.id === p.element_id)) && <Button variant="outline" className="mt-3" onClick={() => set("placements", d.placements.filter(p => model.elements.some(e => e.id === p.element_id)))}>Retirar as cotas dos elementos eliminados</Button>}
      </details>
      <details className="border rounded-lg p-4"><summary className="font-medium cursor-pointer">Negativos · {d.openings.length}</summary>
        <p className="text-xs text-muted-foreground my-3">Volumes retangulares nos eixos locais do elemento: X no seu comprimento, Y na sua largura, Z a partir da sua base. Um negativo parcial é distinguido de uma abertura atravessante. O cálculo gravítico conserva os volumes brutos; o esquema estrutural deve ser adaptado separadamente.</p>
        <div className="space-y-4">{d.openings.map((o, i) => <div key={i} className="border rounded p-3 space-y-3"><div className="grid sm:grid-cols-[1fr_2fr_auto] gap-3 items-end"><TextField label={`Marca do negativo ${i + 1}`} value={o.id} maxLength={60} onChange={v => update("openings", i, { ...o, id: v })} /><ElementSelect model={model} value={o.element_id} label={`Elemento do negativo ${i + 1}`} change={v => update("openings", i, { ...o, element_id: v })} /><Delete label={`Eliminar negativo ${i + 1}`} click={() => remove("openings", i)} /></div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">{[["x_m", "X"], ["y_m", "Y"], ["z_m", "Z"], ["length_m", "Comprimento"], ["width_m", "Largura"], ["height_m", "Altura"]].map(([k, label]) => <NumberField key={k} label={`${o.id} ${label} (m)`} value={o[k]} onChange={v => update("openings", i, { ...o, [k]: v })} />)}</div>
          <TextField label={`Fonte ${o.id}`} value={o.source} onChange={v => update("openings", i, { ...o, source: v })} /></div>)}</div>
        <Button className="mt-3" size="sm" variant="outline" disabled={d.openings.length >= 100} onClick={() => set("openings", [...d.openings, { id: nextId("T", d.openings), element_id: "", x_m: null, y_m: null, z_m: null, length_m: null, width_m: null, height_m: null, source: "" }])}><Plus className="h-4 w-4 mr-1" />Adicionar um negativo</Button>
      </details>
      <details className="border rounded-lg p-4"><summary className="font-medium cursor-pointer">Cortes · {d.cuts.length}</summary>
        <p className="text-xs text-muted-foreground my-3">Um corte X segue o eixo X a Y constante; um corte Y segue o eixo Y a X constante. Os negativos e os elementos rodados são cortados nesta posição.</p>
        <div className="space-y-3">{d.cuts.map((c, i) => <div key={i} className="grid grid-cols-2 sm:grid-cols-[1fr_1fr_1fr_auto] gap-3 items-end"><TextField label={`Marca do corte ${i + 1}`} value={c.id} maxLength={60} onChange={v => update("cuts", i, { ...c, id: v })} /><label className="block text-xs">Eixo horizontal<select aria-label={`Eixo do corte ${i + 1}`} className={`${inputClass} mt-1`} value={c.axis} onChange={e => update("cuts", i, { ...c, axis: e.target.value })}><option value="x">X — Y constant</option><option value="y">Y — X constant</option></select></label><NumberField label={`${c.id} ${c.axis === "x" ? "Y" : "X"} (m)`} value={c.at_m} onChange={v => update("cuts", i, { ...c, at_m: v })} /><Delete label={`Eliminar corte ${i + 1}`} click={() => remove("cuts", i)} /></div>)}</div>
        <Button className="mt-3" variant="outline" size="sm" disabled={d.cuts.length >= 12} onClick={() => set("cuts", [...d.cuts, { id: nextId("S", d.cuts), axis: "x", at_m: null }])}><Plus className="h-4 w-4 mr-1" />Adicionar um corte</Button>
      </details>
      <details className="border rounded-lg p-4"><summary className="font-medium cursor-pointer">Aços desenhados · {d.bars.length} marcas</summary>
        <p className="text-xs text-muted-foreground my-3">Introduza o traçado do primeiro varão nos eixos locais do seu elemento e depois a translação entre varões idênticos. Os pontos são as interseções teóricas antes dos arredondamentos. As marcas automáticas são só de leitura: altere as regras de cálculo para as regenerar. As marcas manuais devem ser justificadas pelo estudo de estruturas.</p>
        <div className="space-y-4">{d.bars.map((b, i) => <details key={i} className="border rounded p-3" open={!b.element_id}><summary className="cursor-pointer text-sm font-medium">{b.mark || "Nova marca"} · {b.element_id || "Elemento a escolher"} · {b.count} HA {b.diameter_mm ?? "?"}</summary><fieldset disabled={!!b.generated_by} className="space-y-3 pt-3 min-w-0">
          {b.generated_by && <p className="text-xs text-emerald-800">Marca automática · alterar as regras e relançar a geração.</p>}
          <div className="grid sm:grid-cols-[1fr_2fr_auto] gap-3 items-end"><TextField label={`Marca do aço ${i + 1}`} value={b.mark} maxLength={60} onChange={v => update("bars", i, { ...b, mark: v })} /><ElementSelect model={model} value={b.element_id} label={`Elemento do aço ${i + 1}`} change={v => update("bars", i, { ...b, element_id: v })} /><Delete label={`Eliminar aço ${i + 1}`} click={() => remove("bars", i)} /></div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{[["diameter_mm", "Diâmetro (mm)"], ["count", "Número"], ["bend_radius_mm", "Raio ao eixo (mm)"], ["cover_mm", "Recobrimento (mm)"]].map(([k, label]) => <NumberField key={k} label={`${b.mark} ${label}`} value={b[k]} step={k === "count" ? "1" : "any"} onChange={v => update("bars", i, { ...b, [k]: v })} />)}</div>
          <div className="space-y-3">{b.points.map((p, j) => <div className="flex items-end gap-2" key={j}><div className="flex-1 min-w-0"><PointFields point={p} label={`${b.mark} P${j + 1}`} change={v => update("bars", i, { ...b, points: b.points.map((q, k) => j === k ? v : q) })} /></div>{b.points.length > 2 && <Delete label={`${b.mark} Eliminar ponto ${j + 1}`} click={() => update("bars", i, { ...b, points: b.points.filter((_, k) => k !== j) })} />}</div>)}</div>
          <Button variant="outline" size="sm" disabled={b.points.length >= 12} onClick={() => update("bars", i, { ...b, points: [...b.points, { x: null, y: null, z: null }] })}>Adicionar um ponto de dobragem</Button>
          <PointFields point={b.repeat} label={`${b.mark} Repetição`} change={v => update("bars", i, { ...b, repeat: v })} />
          <TextField label={`${b.mark} Função`} value={b.role} onChange={v => update("bars", i, { ...b, role: v })} /><TextField label={`${b.mark} Justification / source`} value={b.source} onChange={v => update("bars", i, { ...b, source: v })} />
          {ready && manifest?.schedule.find(r => r.mark === b.mark) && <p className="text-xs text-emerald-900">Comprimento desenvolvido: {manifest.schedule.find(r => r.mark === b.mark).developed_length_m.toFixed(3)} m par barre.</p>}
        </fieldset></details>)}</div>
        <Button className="mt-3" size="sm" variant="outline" disabled={d.bars.length >= 80} onClick={addBar}><Plus className="h-4 w-4 mr-1" />Adicionar uma marca de aço</Button>
      </details>
      <label className="block text-xs">Notas do processo (uma por linha)<textarea aria-label="Notas do processo" className={`${inputClass} mt-1`} rows={3} value={d.notes.join("\n")} onChange={e => set("notes", e.target.value.split("\n"))} /></label>
      <div className="border-t pt-4 space-y-4" data-testid="drawing-output">
        <h3 className="font-medium">Controlos e processo a transferir</h3>
        {dirty && <p role="status" className="text-sm text-amber-800">Guarde o estudo para recalcular os controlos e regenerar as folhas. A pré-visualização anterior está oculta.</p>}
        {sourceStale && <p role="alert" className="text-sm text-red-700">O projeto de licenciamento de origem mudou: crie um novo estudo a partir da sua versão atual.</p>}
        {loading && <p role="status" className="text-sm flex gap-2"><Loader2 className="h-4 w-4 animate-spin" />A preparar as folhas…</p>}
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        {ready && manifest && <>
          {manifest.errors.length > 0 && <div role="alert" className="rounded bg-red-50 p-3 text-sm text-red-800"><b>Geração bloqueada</b><ul className="list-disc ml-5 mt-2">{manifest.errors.map((e, i) => <li key={i}>{e.ref} : {e.message}</li>)}</ul></div>}
          <details className="text-sm" open={!manifest.can_export}><summary className="cursor-pointer">{manifest.warnings.length} pontos a verificar</summary><ul className="list-disc ml-5 mt-2 space-y-1">{manifest.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></details>
          <div className="flex flex-wrap gap-2"><Button disabled={!manifest.can_export} onClick={() => download("plans")}><FileDown className="h-4 w-4 mr-2" />Processo de plantas A3 PDF</Button><Button variant="outline" disabled={!manifest.can_export || !manifest.schedule.length} onClick={() => download("nomenclature")}>Nomenclature CSV</Button><Button variant="outline" onClick={() => download("json")}>Dados do processo JSON</Button></div>
          {manifest.can_export && <><div className="flex flex-col sm:flex-row gap-3 sm:items-center"><label className="text-sm w-full sm:flex-1 min-w-0">Folha<select className={`${inputClass} mt-1`} aria-label="Folha do processo" value={sheet} onChange={e => setSheet(e.target.value)}>{manifest.sheets.map(sh => <option key={sh.id} value={sh.id}>{`${sh.id} · ${sh.title}`}</option>)}</select></label><p className="text-xs text-muted-foreground">{manifest.sheets.length} folhas · {manifest.total_mass_kg.toFixed(2)} kg de aços desenhados</p></div>
            {previewError && <p role="alert" className="text-sm text-red-700">{previewError}</p>}
            {preview ? <img data-testid="drawing-preview" className="block w-full border bg-white rounded" src={preview} alt={`${sheet} — pré-visualização do processo de trabalho A3`} /> : !previewError && <p role="status" className="text-sm">A carregar a folha…</p>}
            {preview && <a className="inline-block text-sm underline" href={preview} target="_blank" rel="noopener noreferrer">Abrir a folha em grande</a>}
            <p className="text-xs text-muted-foreground break-all">Revisão {manifest.revision} · implantação {manifest.drawing_hash.slice(0, 16)} · os controlos geométricos não valem como validação estrutural.</p>
          </>}
        </>}
      </div>
    </>}
  </Card>;
}
