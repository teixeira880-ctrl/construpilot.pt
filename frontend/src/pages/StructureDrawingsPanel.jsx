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
  return <label className="block text-xs min-w-0">{label}<select aria-label={label} className={`${inputClass} mt-1`} value={value} onChange={e => change(e.target.value)}><option value="">Choisir un élément</option>{model.elements.map(e => <option key={e.id} value={e.id}>{`${e.id} · ${e.level}`}</option>)}</select></label>;
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
    }).catch(e => { if (active) setError(e?.response?.status === 409 ? "Cette révision a changé. Rechargez l'étude." : "Contrôle du dossier indisponible. Réessayez en rouvrant l'étude."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [base, study.revision, ready]);
  useEffect(() => {
    let active = true, url = "";
    setPreview(""); setPreviewError("");
    if (!ready || !manifest?.can_export || !sheet) return () => { active = false; };
    api.get(`${base}/drawings/${sheet}`, { params: { expected_revision: study.revision }, responseType: "blob" }).then(({ data }) => {
      if (active) { url = URL.createObjectURL(data); setPreview(url); }
    }).catch(e => { if (active) setPreviewError(e?.response?.status === 409 ? "Planche dépassée. Rechargez l'étude." : "L'aperçu n'a pas pu être chargé."); });
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
    <div className="flex flex-wrap justify-between gap-3"><div><p className="text-xs uppercase tracking-widest text-emerald-800">Atelier plans · A3</p><h2 className="text-xl font-semibold flex items-center gap-2 mt-1"><Layers className="h-5 w-5" />Coffrage, coupes et ferraillage</h2></div>{d && <span className="text-xs rounded-full border px-3 py-2 self-start">{d.basis === "demonstration" ? "Exemple fictif" : "Dossier de travail"} · non exécutoire</span>}</div>
    <p className="text-sm text-muted-foreground">Les planches et le bordereau utilisent les mêmes éléments et tracés. Complétez le dossier, enregistrez l'étude, puis consultez les contrôles et l'aperçu avant de télécharger.</p>
    {!d ? <Button variant="outline" onClick={() => change(empty())}>Préparer le dossier de plans</Button> : <>
      <div className="grid md:grid-cols-4 gap-2 text-xs">{["1 · Éléments et altitudes", "2 · Réservations et coupes", "3 · Tracés d'aciers", "4 · Contrôles et PDF"].map(t => <div key={t} className="bg-emerald-50 rounded px-3 py-2 text-emerald-950">{t}</div>)}</div>
      <details className="border rounded-lg p-4" open={!d.placements.length}>
        <summary className="font-medium cursor-pointer">Implantation et altitudes · {d.placements.length}/{model.elements.length} éléments</summary>
        <p className="text-xs text-muted-foreground my-3">L'origine X/Y, la rotation et les dimensions sont celles du modèle porteur. Indiquez ici l'altitude de la face inférieure de chaque élément, en mètres par rapport au même zéro.</p>
        {!model.elements.length && <p className="text-sm">Ajoutez les éléments porteurs au modèle pour commencer.</p>}
        <div className="space-y-4">{model.elements.map(e => {
          const p = d.placements.find(p => p.element_id === e.id);
          return <div key={e.id} className="grid sm:grid-cols-[1fr_170px_2fr] gap-3 border-b pb-3"><div className="text-sm self-center"><b>{e.id}</b> · {e.level}<p className="text-xs text-muted-foreground">{[e.length_m, e.width_m, e.height_m].map(n => n ?? "?").join(" × ")} m</p></div><NumberField label={`Base ${e.id} (m)`} value={p?.base_z_m} onChange={v => editPlacement(e.id, { base_z_m: v })} /><TextField label={`Source altitude ${e.id}`} value={p?.source} onChange={v => editPlacement(e.id, { source: v })} /></div>;
        })}</div>
        {d.placements.some(p => !model.elements.some(e => e.id === p.element_id)) && <Button variant="outline" className="mt-3" onClick={() => set("placements", d.placements.filter(p => model.elements.some(e => e.id === p.element_id)))}>Retirer les altitudes des éléments supprimés</Button>}
      </details>
      <details className="border rounded-lg p-4"><summary className="font-medium cursor-pointer">Réservations · {d.openings.length}</summary>
        <p className="text-xs text-muted-foreground my-3">Volumes rectangulaires dans les axes locaux de l'élément : X dans sa longueur, Y dans sa largeur, Z depuis sa base. Une réservation partielle est distinguée d'une ouverture traversante. Le calcul gravitaire conserve les volumes bruts ; le schéma porteur doit être adapté séparément.</p>
        <div className="space-y-4">{d.openings.map((o, i) => <div key={i} className="border rounded p-3 space-y-3"><div className="grid sm:grid-cols-[1fr_2fr_auto] gap-3 items-end"><TextField label={`Repère réservation ${i + 1}`} value={o.id} maxLength={60} onChange={v => update("openings", i, { ...o, id: v })} /><ElementSelect model={model} value={o.element_id} label={`Élément réservation ${i + 1}`} change={v => update("openings", i, { ...o, element_id: v })} /><Delete label={`Supprimer réservation ${i + 1}`} click={() => remove("openings", i)} /></div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">{[["x_m", "X"], ["y_m", "Y"], ["z_m", "Z"], ["length_m", "Longueur"], ["width_m", "Largeur"], ["height_m", "Hauteur"]].map(([k, label]) => <NumberField key={k} label={`${o.id} ${label} (m)`} value={o[k]} onChange={v => update("openings", i, { ...o, [k]: v })} />)}</div>
          <TextField label={`Source ${o.id}`} value={o.source} onChange={v => update("openings", i, { ...o, source: v })} /></div>)}</div>
        <Button className="mt-3" size="sm" variant="outline" disabled={d.openings.length >= 100} onClick={() => set("openings", [...d.openings, { id: nextId("T", d.openings), element_id: "", x_m: null, y_m: null, z_m: null, length_m: null, width_m: null, height_m: null, source: "" }])}><Plus className="h-4 w-4 mr-1" />Ajouter une réservation</Button>
      </details>
      <details className="border rounded-lg p-4"><summary className="font-medium cursor-pointer">Coupes · {d.cuts.length}</summary>
        <p className="text-xs text-muted-foreground my-3">Une coupe X suit l'axe X à Y constant ; une coupe Y suit l'axe Y à X constant. Les réservations et les éléments tournés sont découpés à cette position.</p>
        <div className="space-y-3">{d.cuts.map((c, i) => <div key={i} className="grid grid-cols-2 sm:grid-cols-[1fr_1fr_1fr_auto] gap-3 items-end"><TextField label={`Repère coupe ${i + 1}`} value={c.id} maxLength={60} onChange={v => update("cuts", i, { ...c, id: v })} /><label className="block text-xs">Axe horizontal<select aria-label={`Axe coupe ${i + 1}`} className={`${inputClass} mt-1`} value={c.axis} onChange={e => update("cuts", i, { ...c, axis: e.target.value })}><option value="x">X — Y constant</option><option value="y">Y — X constant</option></select></label><NumberField label={`${c.id} ${c.axis === "x" ? "Y" : "X"} (m)`} value={c.at_m} onChange={v => update("cuts", i, { ...c, at_m: v })} /><Delete label={`Supprimer coupe ${i + 1}`} click={() => remove("cuts", i)} /></div>)}</div>
        <Button className="mt-3" variant="outline" size="sm" disabled={d.cuts.length >= 12} onClick={() => set("cuts", [...d.cuts, { id: nextId("S", d.cuts), axis: "x", at_m: null }])}><Plus className="h-4 w-4 mr-1" />Ajouter une coupe</Button>
      </details>
      <details className="border rounded-lg p-4"><summary className="font-medium cursor-pointer">Aciers dessinés · {d.bars.length} repères</summary>
        <p className="text-xs text-muted-foreground my-3">Saisissez le tracé de la première barre dans les axes locaux de son élément, puis la translation entre barres identiques. Les points sont les intersections théoriques avant arrondis. Les repères automatiques sont en lecture seule : modifiez les règles de calcul pour les régénérer. Les repères manuels restent à justifier par l'étude structure.</p>
        <div className="space-y-4">{d.bars.map((b, i) => <details key={i} className="border rounded p-3" open={!b.element_id}><summary className="cursor-pointer text-sm font-medium">{b.mark || "Nouveau repère"} · {b.element_id || "Élément à choisir"} · {b.count} HA {b.diameter_mm ?? "?"}</summary><fieldset disabled={!!b.generated_by} className="space-y-3 pt-3 min-w-0">
          {b.generated_by && <p className="text-xs text-emerald-800">Repère automatique · modifier les règles et relancer la génération.</p>}
          <div className="grid sm:grid-cols-[1fr_2fr_auto] gap-3 items-end"><TextField label={`Repère acier ${i + 1}`} value={b.mark} maxLength={60} onChange={v => update("bars", i, { ...b, mark: v })} /><ElementSelect model={model} value={b.element_id} label={`Élément acier ${i + 1}`} change={v => update("bars", i, { ...b, element_id: v })} /><Delete label={`Supprimer acier ${i + 1}`} click={() => remove("bars", i)} /></div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{[["diameter_mm", "Diamètre (mm)"], ["count", "Nombre"], ["bend_radius_mm", "Rayon à l'axe (mm)"], ["cover_mm", "Enrobage (mm)"]].map(([k, label]) => <NumberField key={k} label={`${b.mark} ${label}`} value={b[k]} step={k === "count" ? "1" : "any"} onChange={v => update("bars", i, { ...b, [k]: v })} />)}</div>
          <div className="space-y-3">{b.points.map((p, j) => <div className="flex items-end gap-2" key={j}><div className="flex-1 min-w-0"><PointFields point={p} label={`${b.mark} P${j + 1}`} change={v => update("bars", i, { ...b, points: b.points.map((q, k) => j === k ? v : q) })} /></div>{b.points.length > 2 && <Delete label={`${b.mark} Supprimer point ${j + 1}`} click={() => update("bars", i, { ...b, points: b.points.filter((_, k) => k !== j) })} />}</div>)}</div>
          <Button variant="outline" size="sm" disabled={b.points.length >= 12} onClick={() => update("bars", i, { ...b, points: [...b.points, { x: null, y: null, z: null }] })}>Ajouter un point de pliage</Button>
          <PointFields point={b.repeat} label={`${b.mark} Répétition`} change={v => update("bars", i, { ...b, repeat: v })} />
          <TextField label={`${b.mark} Rôle`} value={b.role} onChange={v => update("bars", i, { ...b, role: v })} /><TextField label={`${b.mark} Justification / source`} value={b.source} onChange={v => update("bars", i, { ...b, source: v })} />
          {ready && manifest?.schedule.find(r => r.mark === b.mark) && <p className="text-xs text-emerald-900">Longueur développée : {manifest.schedule.find(r => r.mark === b.mark).developed_length_m.toFixed(3)} m par barre.</p>}
        </fieldset></details>)}</div>
        <Button className="mt-3" size="sm" variant="outline" disabled={d.bars.length >= 80} onClick={addBar}><Plus className="h-4 w-4 mr-1" />Ajouter un repère d'acier</Button>
      </details>
      <label className="block text-xs">Notes du dossier (une par ligne)<textarea aria-label="Notes du dossier" className={`${inputClass} mt-1`} rows={3} value={d.notes.join("\n")} onChange={e => set("notes", e.target.value.split("\n"))} /></label>
      <div className="border-t pt-4 space-y-4" data-testid="drawing-output">
        <h3 className="font-medium">Contrôles et dossier à télécharger</h3>
        {dirty && <p role="status" className="text-sm text-amber-800">Enregistrez l'étude pour recalculer les contrôles et régénérer les planches. L'aperçu précédent est masqué.</p>}
        {sourceStale && <p role="alert" className="text-sm text-red-700">Le PC source a changé : créez une nouvelle étude depuis sa version actuelle.</p>}
        {loading && <p role="status" className="text-sm flex gap-2"><Loader2 className="h-4 w-4 animate-spin" />Préparation des planches…</p>}
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        {ready && manifest && <>
          {manifest.errors.length > 0 && <div role="alert" className="rounded bg-red-50 p-3 text-sm text-red-800"><b>Génération bloquée</b><ul className="list-disc ml-5 mt-2">{manifest.errors.map((e, i) => <li key={i}>{e.ref} : {e.message}</li>)}</ul></div>}
          <details className="text-sm" open={!manifest.can_export}><summary className="cursor-pointer">{manifest.warnings.length} points à vérifier</summary><ul className="list-disc ml-5 mt-2 space-y-1">{manifest.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></details>
          <div className="flex flex-wrap gap-2"><Button disabled={!manifest.can_export} onClick={() => download("plans")}><FileDown className="h-4 w-4 mr-2" />Dossier plans A3 PDF</Button><Button variant="outline" disabled={!manifest.can_export || !manifest.schedule.length} onClick={() => download("nomenclature")}>Nomenclature CSV</Button><Button variant="outline" onClick={() => download("json")}>Données du dossier JSON</Button></div>
          {manifest.can_export && <><div className="flex flex-col sm:flex-row gap-3 sm:items-center"><label className="text-sm w-full sm:flex-1 min-w-0">Planche<select className={`${inputClass} mt-1`} aria-label="Planche du dossier" value={sheet} onChange={e => setSheet(e.target.value)}>{manifest.sheets.map(sh => <option key={sh.id} value={sh.id}>{`${sh.id} · ${sh.title}`}</option>)}</select></label><p className="text-xs text-muted-foreground">{manifest.sheets.length} planches · {manifest.total_mass_kg.toFixed(2)} kg d'aciers dessinés</p></div>
            {previewError && <p role="alert" className="text-sm text-red-700">{previewError}</p>}
            {preview ? <img data-testid="drawing-preview" className="block w-full border bg-white rounded" src={preview} alt={`${sheet} — aperçu du dossier de travail A3`} /> : !previewError && <p role="status" className="text-sm">Chargement de la planche…</p>}
            {preview && <a className="inline-block text-sm underline" href={preview} target="_blank" rel="noopener noreferrer">Ouvrir la planche en grand</a>}
            <p className="text-xs text-muted-foreground break-all">Révision {manifest.revision} · empreinte {manifest.drawing_hash.slice(0, 16)} · les contrôles géométriques ne valent pas validation structure.</p>
          </>}
        </>}
      </div>
    </>}
  </Card>;
}
