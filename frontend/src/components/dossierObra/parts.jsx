import { Fragment, useState } from "react";
import { toast } from "sonner";
import { Ruler, Package, Check, Info, ClipboardList, Users, Lock, X } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Pill } from "./common";

export const STAGE_ICONS = { preparar: ClipboardList, medir: Ruler, orcamentar: Package, executar: Users, validar: Check };
export const fmt = (v) => (v === null || v === undefined ? "—" : new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 2 }).format(v));

export function ImpactDialog({ impact, onCancel, onConfirm }) {
  if (!impact) return null;
  return (
    <Dialog open onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="max-w-lg" data-testid="dob-impact-dialog">
        <DialogHeader><DialogTitle>Rever o impacto antes de confirmar</DialogTitle>
          <DialogDescription>{impact.message}</DialogDescription></DialogHeader>
        <div className="grid gap-3 text-sm">
          {impact.impact?.locked && <p className="dob-notice"><Lock size={16} /> {impact.impact.locked_reason}. O compromisso original (orçamento, encomenda ou auto) não é alterado por esta ação.</p>}
          {(impact.impact?.related || []).map((r) => (
            <div key={r.specialty}>
              <p className="font-semibold">{r.label} <span className="text-muted-foreground font-normal">· {r.relation_label}{r.confirmed ? "" : " (por confirmar)"}</span></p>
              {r.items_to_review.length ? <ul className="list-disc ms-5">{r.items_to_review.map((i) => <li key={i.item_id}>{i.title}</li>)}</ul> : <p className="text-muted-foreground">Sem registos a rever.</p>}
            </div>
          ))}
          <p className="text-muted-foreground">Ao confirmar, a alteração fica no histórico e os registos acima são assinalados para revisão.</p>
          <div className="flex justify-end gap-2">
            <button type="button" className="dob-ghost" onClick={onCancel}>Cancelar</button>
            <button type="button" className="dob-primary" onClick={onConfirm} data-testid="dob-impact-confirm">Confirmar alteração</button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Registo novo: no modo Guiado, uma pergunta de cada vez (com «Não sei»); no Técnico, formulário compacto. */
export function AddRecord({ mode, data, cat, fase, local, onSave, initialKind, onClose }) {
  const [step, setStep] = useState(initialKind ? 1 : 0);
  const [f, setF] = useState({ kind: initialKind || "tarefa", title: "", element: "", detail: "", status: "por_fazer", phase: fase || "", location_id: local || "",
    quantity: "", unit: "m²", document: "", revision: "", page: "", scale: "", method: "", source: "manual" });
  const KINDS = [["tarefa", "Uma tarefa a fazer"], ["pendencia", "Uma pendência ou dúvida"], ["verificacao", "Uma verificação"], ["medicao", "Uma medição"],
    ["material", "Um material"], ["registo", "Um registo ou fotografia"], ["alteracao", "Uma alteração"], ["nota", "Uma nota"]];
  const submit = async (unknown = false) => {
    const body = { specialty: data.specialty.key, kind: f.kind, title: f.title.trim() || (unknown ? "Informação por definir" : ""), element: f.element, detail: f.detail,
      status: unknown ? "pendente" : f.status, phase: f.phase || null, location_id: f.location_id || null, source: f.source, revision: f.revision };
    if (!body.title) { toast.error("Indique um título."); return; }
    if (f.kind === "medicao") {
      const q = f.quantity === "" ? null : Number(String(f.quantity).replace(",", "."));
      if (q !== null && (Number.isNaN(q) || q < 0)) { toast.error("Quantidade inválida."); return; }
      body.measurement = { document: f.document, revision: f.revision, page: f.page, element: f.element, scale: f.scale, method: f.method, quantity: q, unit: f.unit };
      if (q !== null) body.quantities = { medida: q };
      if (q === null) body.status = "pendente";
    }
    if (f.kind === "material") body.validation = "por_confirmar";
    await onSave(body);
  };
  if (mode === "guiado") {
    return (
      <div className="dob-card dob-card-pad grid gap-3" data-testid="dob-add-guided">
        <div className="flex items-center justify-between"><p className="font-bold">Registar nesta especialidade</p><button type="button" aria-label="Fechar" onClick={onClose}><X size={18} /></button></div>
        {step === 0 && <><p>O que quer registar?</p><div className="dob-area-grid">{KINDS.map(([k, l]) => <button key={k} type="button" className="dob-area-card" onClick={() => { setF({ ...f, kind: k }); setStep(1); }}>{l}</button>)}</div></>}
        {step === 1 && <>
          <label className="dob-field"><span>{f.kind === "medicao" ? "O que mediu? (ex.: área de cerâmica da fachada norte)" : f.kind === "material" ? "Que material? (ex.: cerâmica 30×60)" : "Descreva em poucas palavras"}</span>
            <input autoFocus value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="dob-add-title" /></label>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="dob-primary" onClick={() => (f.kind === "medicao" ? setStep(2) : submit())} disabled={!f.title.trim()} data-testid="dob-add-next">{f.kind === "medicao" ? "Seguinte" : "Guardar"}</button>
            <button type="button" className="dob-ghost" onClick={() => submit(true)} data-testid="dob-add-unknown">Não sei — fica pendente</button>
          </div>
        </>}
        {step === 2 && <>
          <p>Qual é a quantidade? <span className="text-sm text-muted-foreground">(a área de uma parede é comprimento × altura, sem as janelas)</span></p>
          <div className="flex flex-wrap gap-2 items-end">
            <label className="dob-field"><span>Quantidade</span><input inputMode="decimal" value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })} data-testid="dob-add-qty" /></label>
            <label className="dob-field"><span>Unidade</span><select value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })}>{["m²", "m", "m³", "un", "kg"].map((u) => <option key={u}>{u}</option>)}</select></label>
            <label className="dob-field"><span>De onde vem? (planta, página)</span><input value={f.document} onChange={(e) => setF({ ...f, document: e.target.value })} placeholder="Ex.: Fachadas.pdf, página 2" /></label>
          </div>
          <div className="flex flex-wrap gap-2"><button type="button" className="dob-primary" onClick={() => submit()}>Guardar</button><button type="button" className="dob-ghost" onClick={() => { setF({ ...f, quantity: "" }); submit(true); }}>Não sei — fica pendente</button></div>
        </>}
      </div>
    );
  }
  return (
    <form className="dob-card dob-card-pad grid gap-2" onSubmit={(e) => { e.preventDefault(); submit(); }} data-testid="dob-add-technical">
      <div className="flex items-center justify-between"><p className="font-bold">Novo registo</p><button type="button" aria-label="Fechar" onClick={onClose}><X size={18} /></button></div>
      <div className="grid sm:grid-cols-4 gap-2">
        <label className="dob-field"><span>Tipo</span><select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>{Object.entries(cat.item_kinds).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="dob-field sm:col-span-2"><span>Título</span><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="dob-add-title" /></label>
        <label className="dob-field"><span>Elemento</span><input value={f.element} onChange={(e) => setF({ ...f, element: e.target.value })} /></label>
        <label className="dob-field"><span>Estado</span><select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>{Object.entries(cat.task_status).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="dob-field"><span>Fase</span><select value={f.phase} onChange={(e) => setF({ ...f, phase: e.target.value })}><option value="">Transversal</option>{cat.phases.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}</select></label>
        <label className="dob-field"><span>Local</span><select value={f.location_id} onChange={(e) => setF({ ...f, location_id: e.target.value })}><option value="">Toda a obra</option>{data.locations.map((l) => <option key={l.location_id} value={l.location_id}>{l.path}</option>)}</select></label>
        <label className="dob-field"><span>Origem</span><select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}>{Object.entries(cat.sources).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
      </div>
      {f.kind === "medicao" && <div className="grid sm:grid-cols-4 gap-2">
        {[["document", "Documento"], ["revision", "Revisão"], ["page", "Página/elemento"], ["scale", "Escala"], ["method", "Método"], ["quantity", "Quantidade"]].map(([k, l]) =>
          <label key={k} className="dob-field"><span>{l}</span><input value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} inputMode={k === "quantity" ? "decimal" : undefined} /></label>)}
        <label className="dob-field"><span>Unidade</span><select value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })}>{["m²", "m", "m³", "un", "kg"].map((u) => <option key={u}>{u}</option>)}</select></label>
      </div>}
      <label className="dob-field"><span>Detalhe / especificação / referência</span><textarea rows={2} value={f.detail} onChange={(e) => setF({ ...f, detail: e.target.value })} /></label>
      <div><button type="submit" className="dob-primary" data-testid="dob-add-save">Guardar registo</button></div>
    </form>
  );
}

export function LayersBlock({ item, mode, onValidate }) {
  const [openRow, setOpenRow] = useState(null);
  const [fix, setFix] = useState("");
  const LBL = { por_confirmar: "A confirmar", confirmado: "Confirmado", corrigido: "Corrigido", rejeitado: "Rejeitado", validado: "Validado" };
  return (
    <ol className="dob-layers" data-testid={`dob-layers-${item.item_id}`}>
      {(item.layers || []).map((l) => {
        const isOpen = openRow === l.order;
        return (
          <li key={l.order}>
            <button type="button" className="dob-layer" aria-expanded={isOpen} onClick={() => { setOpenRow(isOpen ? null : l.order); setFix(l.material || ""); }} data-testid={`dob-layer-${l.order}`}>
              <span className="dob-layer-n" aria-hidden="true">{l.order}</span>
              <span className="dob-layer-name">{l.name}{l.material && l.validation !== "por_confirmar" ? <small>{l.material}</small> : null}</span>
              {l.validation !== "confirmado" || mode === "tecnico" ? <span className={`dob-pill dob-pill-${l.validation}`}>{LBL[l.validation]}</span> : null}
            </button>
            {isOpen && (
              <div className="dob-layer-detail">
                <p className="text-xs text-muted-foreground">{{ extraido: "Extraído de documento", manual: "Introduzido manualmente", inferido: "Inferido — a confirmar" }[l.source]}{l.reference ? ` · ${l.reference}` : ""}{l.material ? ` · ${l.material}` : ""}</p>
                <form className="flex flex-wrap gap-2 items-end" onSubmit={(e) => { e.preventDefault(); onValidate(item, { action: "corrigir", layer_order: l.order, material: fix }).then(() => setOpenRow(null)); }}>
                  <button type="button" className="dob-ghost dob-sm" onClick={() => onValidate(item, { action: "confirmar", layer_order: l.order }).then(() => setOpenRow(null))} data-testid={`dob-layer-confirm-${l.order}`}>Confirmar</button>
                  <label className="dob-field flex-1 min-w-36"><span className="sr-only">Material correto</span><input value={fix} onChange={(e) => setFix(e.target.value)} placeholder="Material correto" data-testid="dob-layer-fix-input" /></label>
                  <button type="submit" className="dob-ghost dob-sm" disabled={!fix.trim()} data-testid={`dob-layer-fix-${l.order}`}>Corrigir</button>
                  <button type="button" className="dob-ghost dob-sm" onClick={() => onValidate(item, { action: "rejeitar", layer_order: l.order }).then(() => setOpenRow(null))}>Rejeitar</button>
                </form>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function Origin({ m }) {
  if (!m) return null;
  const rows = [["Documento", m.document], ["Revisão", m.revision], ["Página", m.page], ["Elemento", m.element], ["Escala", m.scale], ["Método", m.method],
    ["Quantidade", m.quantity !== null && m.quantity !== undefined ? `${fmt(m.quantity)} ${m.unit || ""}` : "Por medir"]];
  return <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm" data-testid="dob-origin">{rows.map(([k, v]) => <Fragment key={k}><dt className="text-muted-foreground">{k}</dt><dd>{v || "—"}</dd></Fragment>)}</dl>;
}

export function QuantitiesTable({ item, cat, onSave }) {
  const [q, setQ] = useState(item.quantities || {});
  const unit = item.measurement?.unit || "";
  return (
    <div className="overflow-x-auto">
      <table className="dob-table" data-testid={`dob-quantities-${item.item_id}`}>
        <thead><tr>{cat.quantity_kinds.map((k) => <th key={k.key} scope="col">{k.label}</th>)}<th /></tr></thead>
        <tbody><tr>
          {cat.quantity_kinds.map((k) => <td key={k.key}><label className="sr-only" htmlFor={`q-${item.item_id}-${k.key}`}>{k.label}</label>
            <input id={`q-${item.item_id}-${k.key}`} inputMode="decimal" value={q[k.key] ?? ""} placeholder="—" onChange={(e) => setQ({ ...q, [k.key]: e.target.value })} /> <span className="text-xs">{unit}</span></td>)}
          <td><button type="button" className="dob-ghost" style={{ minHeight: 32 }} onClick={() => {
            const out = {};
            for (const [k, v] of Object.entries(q)) { if (v === "" || v === null || v === undefined) continue; const n = Number(String(v).replace(",", ".")); if (Number.isNaN(n) || n < 0) { toast.error(`Valor inválido: ${k}`); return; } out[k] = n; }
            onSave(item, { quantities: out });
          }}>Guardar</button></td>
        </tr></tbody>
      </table>
      <p className="dob-hint mt-1"><Info size={13} /> Cada quantidade é guardada à parte: medir não é o mesmo que orçamentar, encomendar, executar ou faturar.</p>
    </div>
  );
}

