import React, { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Calculator, Plus, Trash2 } from "lucide-react";

const sel = "border rounded-md p-2 bg-background text-sm w-full";
const toNum = v => (v === "" || v === null || v === undefined ? null : Number(v));
const clampFck = v => Math.min(50, Math.max(12, Number(v) || 25));
const fctmOf = v => Number((0.3 * Math.pow(clampFck(v), 2 / 3)).toFixed(3));
const DEF_SRC = "Introdução manual — a verificar pelo engenheiro";
const cm2 = v => (v == null ? "—" : (Number(v) / 100).toFixed(2));

const defaultMat = ec2opts => ({
  fck_mpa: clampFck(ec2opts?.fck), fyk_mpa: Math.min(600, Math.max(400, Number(ec2opts?.fyk) || 500)),
  fctm_mpa: fctmOf(ec2opts?.fck), gamma_c: Number(ec2opts?.gamma_c) || 1.5,
  gamma_s: Number(ec2opts?.gamma_s) || 1.15, alpha_cc: Number(ec2opts?.alpha_cc) || 1.0,
  source: "Materiais usuais do Anexo Nacional português — a verificar",
});

function Num({ label, value, onChange, testid, disabled }) {
  return <label className="block text-xs min-w-0">{label}<Input aria-label={label} data-testid={testid} disabled={disabled} type="number" step="any" className="mt-1" value={value ?? ""} onChange={e => onChange(toNum(e.target.value))} /></label>;
}
function Txt({ label, value, onChange, testid }) {
  return <label className="block text-xs min-w-0">{label}<Input aria-label={label} data-testid={testid} className="mt-1" value={value ?? ""} onChange={e => onChange(e.target.value)} /></label>;
}
const Status = ({ s }) => {
  const ok = ["partial", "pass", "listed_checks_only"].includes(s);
  const bad = ["fails_check", "out_of_scope", "conflict", "conflicts", "incomplete", "has_unresolved_checks", "blocked"].includes(s);
  const map = { partial: "Calculado", pass: "Conforme (introduzido)", conflict: "Conflito", conflicts: "Conflits", incomplete: "A completar", fails_check: "Controlo não satisfeito", out_of_scope: "Hors domaine", listed_checks_only: "Controlos listados", has_unresolved_checks: "Controlos a rever", blocked: "Bloqueado" };
  return <span className={bad ? "text-red-700 font-semibold" : ok ? "text-emerald-700" : "text-muted-foreground"}>{map[s] || s}</span>;
};

export default function StructureManualPanels({ study, model, setModel, dirty, save, envelope, ec2opts, busy }) {
  const [mat, setMat] = useState(() => defaultMat(ec2opts));
  useEffect(() => {
    const m = model?.reinforcement?.sections?.[0]?.materials || model?.linked_sections?.[0]?.materials;
    if (m) setMat(m);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [study?.study_id]);

  const beams = (model?.elements || []).filter(e => e.kind === "beam");
  const combos = model?.combinations || [];
  const envById = Object.fromEntries((envelope?.elements || []).map(e => [e.id, e]));
  const autoDesigns = Object.fromEntries(((study?.automation_result?.designs) || []).filter(d => d.kind === "beam").map(d => [d.element_id, d]));
  const result = study?.result || {};
  const cover = () => Number(ec2opts?.cover_m) || 0.05;
  const cot = () => Number(ec2opts?.cot_theta) || 2.5;

  const applyMat = next => {
    setMat(next);
    setModel(m => ({
      ...m,
      ...(m.reinforcement ? { reinforcement: { ...m.reinforcement, sections: (m.reinforcement.sections || []).map(s => ({ ...s, materials: next })) } } : {}),
      ...(Array.isArray(m.linked_sections) && m.linked_sections.length ? { linked_sections: m.linked_sections.map(l => ({ ...l, materials: next })) } : {}),
    }));
  };

  const dirtyHint = dirty && <p className="text-xs text-amber-800" role="status">Alterações não guardadas — clique em «Guardar e recalcular» para atualizar os resultados.</p>;
  const MaterialsEditor = ({ testPrefix }) => <div className="grid grid-cols-2 md:grid-cols-4 gap-3 border rounded-lg p-3">
    <p className="col-span-2 md:col-span-4 text-xs font-medium text-muted-foreground">Materiais betão/aço (aplicados a todas as secções)</p>
    <Num label="fck (MPa)" value={mat.fck_mpa} onChange={v => applyMat({ ...mat, fck_mpa: v, fctm_mpa: fctmOf(v) })} testid={`${testPrefix}-fck`} />
    <Num label="fyk (MPa)" value={mat.fyk_mpa} onChange={v => applyMat({ ...mat, fyk_mpa: v })} />
    <Num label="fctm (MPa)" value={mat.fctm_mpa} onChange={v => applyMat({ ...mat, fctm_mpa: v })} />
    <Num label="αcc" value={mat.alpha_cc} onChange={v => applyMat({ ...mat, alpha_cc: v })} />
    <Num label="γc" value={mat.gamma_c} onChange={v => applyMat({ ...mat, gamma_c: v })} />
    <Num label="γs" value={mat.gamma_s} onChange={v => applyMat({ ...mat, gamma_s: v })} />
    <Txt label="Fonte dos materiais" value={mat.source} onChange={v => applyMat({ ...mat, source: v })} />
  </div>;

  // ---------- Reinforcement (ferraillage manuel / relevé) ----------
  const rf = model?.reinforcement;
  const enableReinf = () => setModel(m => ({ ...m, reinforcement: { basis: "design_draft", sources: [], observations: [], sections: [], footings: [], schedules: [] } }));
  const setReinf = patch => setModel(m => ({ ...m, reinforcement: { ...m.reinforcement, ...patch } }));
  const sectionFromBeam = e => {
    const uls = (envById[e.id] || {}).uls || {};
    const h = e.height_m ? e.height_m * 1000 : 500, b = e.width_m ? e.width_m * 1000 : 300;
    return {
      id: `S_${e.id}`.slice(0, 60), kind: "beam", b_mm: b, h_mm: h, d_mm: Math.max(10, h - cover() * 1000),
      med_knm: (uls.moment_knm?.value) ?? 0, ved_kn: Math.abs((uls.shear_kn?.value) ?? 0), ned_kn: 0, torsion_knm: 0,
      materials: mat, as_provided_mm2: autoDesigns[e.id]?.as_provided_mm2 ?? null, cot_theta: cot(),
      source: DEF_SRC, case: uls.moment_knm?.label || "Caso manual",
    };
  };
  const prefillSections = () => setReinf({ sections: beams.map(sectionFromBeam) });
  const addSection = () => setModel(m => {
    let n = 1; const s = m.reinforcement.sections || []; while (s.some(x => x.id === `S${n}`)) n++;
    return { ...m, reinforcement: { ...m.reinforcement, sections: [...s, { id: `S${n}`, kind: "beam", b_mm: 300, h_mm: 500, d_mm: 450, med_knm: 0, ved_kn: 0, ned_kn: 0, torsion_knm: 0, materials: mat, as_provided_mm2: null, cot_theta: cot(), source: DEF_SRC, case: "Caso manual" }] } };
  });
  const editSection = (i, patch) => setModel(m => ({ ...m, reinforcement: { ...m.reinforcement, sections: m.reinforcement.sections.map((s, j) => j === i ? { ...s, ...patch, ...(patch.kind === "slab_strip" ? { b_mm: 1000 } : {}) } : s) } }));
  const removeSection = i => setModel(m => ({ ...m, reinforcement: { ...m.reinforcement, sections: m.reinforcement.sections.filter((_, j) => j !== i) } }));
  const reinfResults = Object.fromEntries(((result.reinforcement?.sections) || []).map(r => [r.id, r]));

  // ---------- Architecture (gabarits & hauteurs libres) ----------
  const ar = model?.architecture;
  const enableArch = () => setModel(m => ({ ...m, architecture: { clearances: [], fit_bands: [], unresolved: [] } }));
  const setArch = patch => setModel(m => ({ ...m, architecture: { ...m.architecture, ...patch } }));
  const clearanceFromBeam = e => ({ id: `C_${e.id}`.slice(0, 60), element_id: e.id, label: `Altura livre sob ${e.id}`, pc_clearance_m: 2.5, integrated_depth_m: 0, additional_loss_m: 0, minimum_clearance_m: 2.1, source: DEF_SRC, criterion_source: DEF_SRC });
  const prefillClearances = () => setArch({ clearances: beams.map(clearanceFromBeam) });
  const editArr = (key, i, patch) => setModel(m => ({ ...m, architecture: { ...m.architecture, [key]: m.architecture[key].map((r, j) => j === i ? { ...r, ...patch } : r) } }));
  const removeArr = (key, i) => setModel(m => ({ ...m, architecture: { ...m.architecture, [key]: m.architecture[key].filter((_, j) => j !== i) } }));
  const addFitBand = () => setModel(m => {
    let n = 1; const fb = m.architecture.fit_bands || []; while (fb.some(x => x.id === `F${n}`)) n++;
    return { ...m, architecture: { ...m.architecture, fit_bands: [...fb, { id: `F${n}`, element_id: beams[0]?.id || (m.elements[0]?.id || ""), label: "Gabarito", axis: "x", minimum_m: 0, maximum_m: 1, mode: "beam_width", source: DEF_SRC }] } };
  });
  const archChecks = Object.fromEntries(((result.architectural_compatibility?.checks) || []).map(c => [c.id, c]));

  // ---------- Linked reinforcement (sections liées aux efforts) ----------
  const links = model?.linked_sections || [];
  const linkFromBeam = e => ({ id: `L_${e.id}`.slice(0, 60), element_id: e.id, case_ids: combos.map(c => c.id), kind: "beam", tension_centroid_from_face_mm: cover() * 1000 + 8, materials: mat, as_provided_mm2: autoDesigns[e.id]?.as_provided_mm2 ?? null, cot_theta: cot(), uniform_across_width: false, source: DEF_SRC });
  const prefillLinks = () => setModel(m => ({ ...m, linked_sections: beams.map(linkFromBeam) }));
  const addLink = () => setModel(m => {
    const e = beams[0]; if (!e) return m; let n = 1; while ((m.linked_sections || []).some(x => x.id === `L${n}`)) n++;
    return { ...m, linked_sections: [...(m.linked_sections || []), { ...linkFromBeam(e), id: `L${n}` }] };
  });
  const editLink = (i, patch) => setModel(m => ({ ...m, linked_sections: m.linked_sections.map((l, j) => j === i ? { ...l, ...patch } : l) }));
  const removeLink = i => setModel(m => ({ ...m, linked_sections: m.linked_sections.filter((_, j) => j !== i) }));
  const linkResults = Object.fromEntries(((result.linked_reinforcement?.sections) || []).map(r => [r.id, r]));
  const toggleCase = (i, id, on, cur) => editLink(i, { case_ids: on ? [...cur, id] : cur.filter(x => x !== id) });

  return <>
    <Card className="p-5 space-y-3" data-testid="reinforcement-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Armaduras manuais NP EN 1992 (secções independentes)</h2>
        <Button size="sm" onClick={save} disabled={busy} data-testid="manual-save-reinf"><Calculator className="h-4 w-4 mr-2" />Guardar e recalcular</Button>
      </div>
      <p className="text-sm text-muted-foreground">Verifica o aço necessário em secções com esforços <b>introduzidos à mão</b> (M, V independentes), independentemente da descida de cargas. Pré-preenchimento automático possível a partir da envolvente NP EN 1990, com edição livre. Relatório <b>indicatif</b>, a validar pelo engenheiro.</p>
      {!rf ? <Button variant="outline" onClick={enableReinf} data-testid="reinf-enable"><Plus className="h-4 w-4 mr-1" />Ativar as armaduras manuais</Button> : <>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-2">Natureza do processo
            <select className={sel + " max-w-xs"} value={rf.basis} onChange={e => setReinf({ basis: e.target.value })} data-testid="reinf-basis">
              <option value="design_draft">Avant-projet (design_draft)</option>
              <option value="source_replay">Registo da fonte (source_replay)</option>
            </select>
          </label>
        </div>
        <MaterialsEditor testPrefix="reinf-mat" />
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={prefillSections} disabled={!beams.length} data-testid="reinf-prefill"><Plus className="h-4 w-4 mr-1" />Pré-preencher a partir das vigas (envolvente)</Button>
          <Button variant="outline" size="sm" onClick={addSection} data-testid="reinf-add"><Plus className="h-4 w-4 mr-1" />Adicionar uma secção</Button>
        </div>
        <div className="space-y-3">{(rf.sections || []).map((s, i) => { const res = reinfResults[s.id]; return <div key={i} className="border rounded-lg p-3 space-y-3" data-testid={`reinf-section-${i}`}>
          <div className="flex flex-wrap items-center gap-2">
            <Input aria-label={`Marca da secção ${i + 1}`} className="max-w-[9rem]" value={s.id} onChange={e => editSection(i, { id: e.target.value })} />
            <select aria-label={`Tipo de secção ${i + 1}`} className={sel + " max-w-[10rem]"} value={s.kind} onChange={e => editSection(i, { kind: e.target.value })}><option value="beam">Viga</option><option value="slab_strip">Faixa de laje (1 m)</option></select>
            {res && <span className="text-xs">→ <Status s={res.status} />{res.as_required_mm2 != null ? ` · As,req ${cm2(res.as_required_mm2)} cm²` : ""}</span>}
            <Button variant="ghost" size="sm" aria-label={`Eliminar secção ${i + 1}`} onClick={() => removeSection(i)}><Trash2 className="h-4 w-4" /></Button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Num label="b (mm)" value={s.b_mm} onChange={v => editSection(i, { b_mm: v })} disabled={s.kind === "slab_strip"} />
            <Num label="h (mm)" value={s.h_mm} onChange={v => editSection(i, { h_mm: v })} />
            <Num label="d utile (mm)" value={s.d_mm} onChange={v => editSection(i, { d_mm: v })} />
            <Num label="cot θ (1–2,5)" value={s.cot_theta} onChange={v => editSection(i, { cot_theta: v })} />
            <Num label="M Ed (kN·m)" value={s.med_knm} onChange={v => editSection(i, { med_knm: v })} testid={`reinf-med-${i}`} />
            <Num label="V Ed (kN)" value={s.ved_kn} onChange={v => editSection(i, { ved_kn: v })} />
            <Num label="As colocado (mm², opcional)" value={s.as_provided_mm2} onChange={v => editSection(i, { as_provided_mm2: v })} />
            <Txt label="Caso / combinação" value={s.case} onChange={v => editSection(i, { case: v })} />
          </div>
          <Txt label="Source / justification" value={s.source} onChange={v => editSection(i, { source: v })} />
          {res && res.issues?.length > 0 && <ul className="list-disc ml-5 text-[11px] text-amber-700">{res.issues.map((x, k) => <li key={k}>{x}</li>)}</ul>}
        </div>; })}</div>
        {dirtyHint}
        {result.reinforcement && <p className="text-[11px] text-muted-foreground" data-testid="reinf-results">{result.reinforcement.sections?.length || 0} secção(ões) calculada(s) · ELS fendilhação/flecha, amarrações e disposições construtivas não verificadas — a validar.</p>}
      </>}
    </Card>

    <Card className="p-5 space-y-3" data-testid="architecture-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Controlos de arquitetura do projeto de licenciamento (gabaritos &amp; alturas livres)</h2>
        <Button size="sm" onClick={save} disabled={busy} data-testid="manual-save-arch"><Calculator className="h-4 w-4 mr-2" />Guardar e recalcular</Button>
      </div>
      <p className="text-sm text-muted-foreground">Verifica restrições <b>introduzidas explicitamente</b> do projeto de licenciamento (altura livre sob viga, saliências numa faixa). Nenhuma deteção automática nem validação do projeto. Pré-preenchimento proposto, editável. Relatório <b>indicatif</b>.</p>
      {!ar ? <Button variant="outline" onClick={enableArch} data-testid="arch-enable"><Plus className="h-4 w-4 mr-1" />Ativar os controlos de arquitetura</Button> : <>
        {result.architectural_compatibility && <p className="text-xs">Estado global: <Status s={result.architectural_compatibility.status} /></p>}
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={prefillClearances} disabled={!beams.length} data-testid="arch-prefill"><Plus className="h-4 w-4 mr-1" />Pré-preencher as alturas livres (vigas)</Button>
          <Button variant="outline" size="sm" onClick={addFitBand} data-testid="arch-add-fitband"><Plus className="h-4 w-4 mr-1" />Adicionar um gabarito</Button>
        </div>
        <div className="space-y-3"><h3 className="text-sm font-medium">Alturas livres</h3>{(ar.clearances || []).map((c, i) => { const res = archChecks[c.id]; return <div key={i} className="border rounded-lg p-3 space-y-3" data-testid={`arch-clearance-${i}`}>
          <div className="flex flex-wrap items-center gap-2">
            <Input aria-label={`Marca da altura ${i + 1}`} className="max-w-[8rem]" value={c.id} onChange={e => editArr("clearances", i, { id: e.target.value })} />
            <select aria-label={`Elemento da altura ${i + 1}`} className={sel + " max-w-[10rem]"} value={c.element_id} onChange={e => editArr("clearances", i, { element_id: e.target.value })}><option value="">Viga…</option>{beams.map(e => <option key={e.id} value={e.id}>{e.id}</option>)}</select>
            {res && <span className="text-xs">→ <Status s={res.status} />{res.margin_m != null ? ` · marge ${(res.margin_m * 100).toFixed(1)} cm` : ""}</span>}
            <Button variant="ghost" size="sm" aria-label={`Eliminar altura ${i + 1}`} onClick={() => removeArr("clearances", i)}><Trash2 className="h-4 w-4" /></Button>
          </div>
          <Txt label="Descrição" value={c.label} onChange={v => editArr("clearances", i, { label: v })} />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Num label="Altura bruta do projeto (m)" value={c.pc_clearance_m} onChange={v => editArr("clearances", i, { pc_clearance_m: v })} />
            <Num label="Profundidade integrada (m)" value={c.integrated_depth_m} onChange={v => editArr("clearances", i, { integrated_depth_m: v })} />
            <Num label="Perda complementar (m)" value={c.additional_loss_m} onChange={v => editArr("clearances", i, { additional_loss_m: v })} />
            <Num label="Altura livre mínima (m)" value={c.minimum_clearance_m} onChange={v => editArr("clearances", i, { minimum_clearance_m: v })} />
          </div>
          <div className="grid md:grid-cols-2 gap-3"><Txt label="Fonte da cota" value={c.source} onChange={v => editArr("clearances", i, { source: v })} /><Txt label="Fonte do critério" value={c.criterion_source} onChange={v => editArr("clearances", i, { criterion_source: v })} /></div>
          {res?.summary && <p className="text-[11px] text-muted-foreground">{res.summary}</p>}
        </div>; })}</div>
        {(ar.fit_bands || []).length > 0 && <div className="space-y-3"><h3 className="text-sm font-medium">Gabaritos (faixas disponíveis)</h3>{(ar.fit_bands || []).map((c, i) => { const res = archChecks[c.id]; return <div key={i} className="border rounded-lg p-3 space-y-3" data-testid={`arch-fitband-${i}`}>
          <div className="flex flex-wrap items-center gap-2">
            <Input aria-label={`Marca do gabarito ${i + 1}`} className="max-w-[8rem]" value={c.id} onChange={e => editArr("fit_bands", i, { id: e.target.value })} />
            <select aria-label={`Elemento do gabarito ${i + 1}`} className={sel + " max-w-[10rem]"} value={c.element_id} onChange={e => editArr("fit_bands", i, { element_id: e.target.value })}><option value="">Elemento…</option>{(model.elements || []).map(e => <option key={e.id} value={e.id}>{e.id}</option>)}</select>
            <select aria-label={`Modo gabarito ${i + 1}`} className={sel + " max-w-[11rem]"} value={c.mode} onChange={e => editArr("fit_bands", i, { mode: e.target.value })}><option value="beam_width">Largura da viga</option><option value="column_footprint">Implantação do pilar</option></select>
            <select aria-label={`Eixo do gabarito ${i + 1}`} className={sel + " max-w-[6rem]"} value={c.axis} onChange={e => editArr("fit_bands", i, { axis: e.target.value })}><option value="x">Eixo X</option><option value="y">Eixo Y</option></select>
            {res && <span className="text-xs">→ <Status s={res.status} /></span>}
            <Button variant="ghost" size="sm" aria-label={`Eliminar gabarito ${i + 1}`} onClick={() => removeArr("fit_bands", i)}><Trash2 className="h-4 w-4" /></Button>
          </div>
          <Txt label="Descrição" value={c.label} onChange={v => editArr("fit_bands", i, { label: v })} />
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <Num label="Faixa mínima (m)" value={c.minimum_m} onChange={v => editArr("fit_bands", i, { minimum_m: v })} />
            <Num label="Faixa máxima (m)" value={c.maximum_m} onChange={v => editArr("fit_bands", i, { maximum_m: v })} />
            <Txt label="Fonte" value={c.source} onChange={v => editArr("fit_bands", i, { source: v })} />
          </div>
          {res?.summary && <p className="text-[11px] text-muted-foreground">{res.summary}</p>}
        </div>; })}</div>}
        {result.architectural_compatibility?.issues?.length > 0 && <ul className="list-disc ml-5 text-[11px] text-amber-700" data-testid="arch-issues">{result.architectural_compatibility.issues.map((x, k) => <li key={k}>{x}</li>)}</ul>}
        {dirtyHint}
      </>}
    </Card>

    <Card className="p-5 space-y-3" data-testid="linked-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Aços ligados aos esforços reais (NP EN 1992 · envolvente)</h2>
        <Button size="sm" onClick={save} disabled={busy} data-testid="manual-save-linked"><Calculator className="h-4 w-4 mr-2" />Guardar e recalcular</Button>
      </div>
      <p className="text-sm text-muted-foreground">Verifica aços <b>saisis</b> contra os esforços <b>calculados pela descida de cargas</b> (cada combinação verificada separadamente, nenhuma envolvente inventada). Pré-preenchimento a partir das vigas e dos aços da cadeia automática. Relatório <b>indicatif</b>, a validar.</p>
      {!combos.length && <p className="text-sm text-amber-800" data-testid="linked-no-combos">Gere primeiro as combinações Eurocódigo NP EN 1990 para ligar secções aos esforços.</p>}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={prefillLinks} disabled={!beams.length || !combos.length} data-testid="linked-prefill"><Plus className="h-4 w-4 mr-1" />Pré-preencher a partir das vigas</Button>
        <Button variant="outline" size="sm" onClick={addLink} disabled={!beams.length || !combos.length} data-testid="linked-add"><Plus className="h-4 w-4 mr-1" />Adicionar uma secção ligada</Button>
      </div>
      {links.length > 0 && <MaterialsEditor testPrefix="linked-mat" />}
      <div className="space-y-3">{links.map((l, i) => { const res = linkResults[l.id]; return <div key={i} className="border rounded-lg p-3 space-y-3" data-testid={`linked-section-${i}`}>
        <div className="flex flex-wrap items-center gap-2">
          <Input aria-label={`Marca ligada ${i + 1}`} className="max-w-[8rem]" value={l.id} onChange={e => editLink(i, { id: e.target.value })} />
          <select aria-label={`Viga ligada ${i + 1}`} className={sel + " max-w-[9rem]"} value={l.element_id} onChange={e => editLink(i, { element_id: e.target.value })}><option value="">Viga…</option>{beams.map(e => <option key={e.id} value={e.id}>{e.id}</option>)}</select>
          <select aria-label={`Tipo ligado ${i + 1}`} className={sel + " max-w-[10rem]"} value={l.kind} onChange={e => editLink(i, { kind: e.target.value })}><option value="beam">Viga</option><option value="slab_strip">Faixa de laje</option></select>
          {res && <span className="text-xs">→ <Status s={res.status} />{res.as_required_envelope_mm2 != null ? ` · As,req ${cm2(res.as_required_envelope_mm2)} cm²` : ""}</span>}
          <Button variant="ghost" size="sm" aria-label={`Eliminar ligado ${i + 1}`} onClick={() => removeLink(i)}><Trash2 className="h-4 w-4" /></Button>
        </div>
        <div>
          <p className="text-xs font-medium mb-1">Combinações verificadas</p>
          <div className="flex flex-wrap gap-3">{combos.map(c => <label key={c.id} className="flex items-center gap-1 text-xs"><input type="checkbox" checked={l.case_ids.includes(c.id)} onChange={e => toggleCase(i, c.id, e.target.checked, l.case_ids)} data-testid={`linked-case-${i}-${c.id}`} />{c.id}</label>)}</div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Num label="Centro dos aços / face tracionada (mm)" value={l.tension_centroid_from_face_mm} onChange={v => editLink(i, { tension_centroid_from_face_mm: v })} />
          <Num label="As colocado (mm², opcional)" value={l.as_provided_mm2} onChange={v => editLink(i, { as_provided_mm2: v })} testid={`linked-asprov-${i}`} />
          <Num label="cot θ (1–2,5)" value={l.cot_theta} onChange={v => editLink(i, { cot_theta: v })} />
          {l.kind === "slab_strip" && <label className="flex items-end gap-2 text-xs"><input type="checkbox" checked={!!l.uniform_across_width} onChange={e => editLink(i, { uniform_across_width: e.target.checked })} />Distribuição uniforme na largura</label>}
        </div>
        <Txt label="Source / justification" value={l.source} onChange={v => editLink(i, { source: v })} />
        {res && res.governing_flexure_case && <p className="text-[11px] text-muted-foreground">Caso condicionante: {res.governing_flexure_case} · vão {res.span_m} m · {res.force_basis}</p>}
      </div>; })}</div>
      {result.linked_reinforcement?.unresolved && links.length > 0 && <p className="text-[11px] text-muted-foreground" data-testid="linked-results">{result.linked_reinforcement.scope}</p>}
      {dirtyHint}
    </Card>
  </>;
}
