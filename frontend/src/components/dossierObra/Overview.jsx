import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { HardHat, FileText, Target, AlertTriangle, Inbox, Plus, Check, Link2, MapPin, Info, CalendarRange, ArrowRight, Layers } from "lucide-react";
import { api } from "@/lib/api";
import { Pill, errMsg, useDossierContext } from "./common";
import { ModuleIcon } from "./icons";

function Header({ ov, base, qs }) {
  const c = ov.chantier;
  return (
    <header className="dob-head">
      <div className="dob-title">
        <span className="dob-title-icon"><HardHat size={28} aria-hidden="true" /></span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2"><h1 data-testid="dob-obra-name">{c.name}</h1>{c.demo && <span className="dob-demo">Exemplo demonstrativo</span>}</div>
          <p className="dob-sub">{[c.ref || c.chantier_id, c.client_name, [c.address, c.city].filter(Boolean).join(", ")].filter(Boolean).join(" · ")}</p>
        </div>
      </div>
      <Link to={`${base}/compilar${qs()}`} className="dob-primary" data-testid="dob-compile-btn"><FileText size={20} /> Compilar dossier</Link>
    </header>
  );
}

function GuidedStart({ ov, cat, onStart }) {
  const [area, setArea] = useState(null);
  const enabled = new Set(ov.enabled);
  const areaObj = cat.areas.find((a) => a.key === area);
  return (
    <section className="dob-card dob-card-pad grid gap-4" data-testid="dob-guided-start">
      <div>
        <h2 className="text-xl font-bold">Por onde quer começar?</h2>
        <p className="text-sm text-muted-foreground">Escolha uma área. Pode trabalhar numa só especialidade sem configurar a obra inteira.</p>
      </div>
      <div className="dob-area-grid">
        {cat.areas.map((a) => {
          return (
            <button key={a.key} type="button" className="dob-area-card" aria-pressed={area === a.key} onClick={() => setArea(a.key)} data-testid={`dob-start-area-${a.key}`}>
              <span className="flex items-center gap-3 font-bold"><ModuleIcon area={a.key} size={18} tile={36} /> {a.label}</span>
              <span className="text-sm text-muted-foreground">{a.description}</span>
            </button>
          );
        })}
      </div>
      {areaObj && (
        <div className="grid gap-2" data-testid="dob-start-specialties">
          <p className="font-semibold">Qual destes trabalhos?</p>
          <div className="dob-area-grid">
            {areaObj.specialties.map((s) => (
              <button key={s.key} type="button" className="dob-area-card" onClick={() => onStart(s.key)} data-testid={`dob-start-${s.key}`}>
                <span className="flex items-center gap-3 font-bold"><ModuleIcon k={s.key} area={s.area} size={16} tile={32} /><span className="flex-1">{s.label}</span>{enabled.has(s.key) && <Pill s="validado">Ativa</Pill>}</span>
                <span className="text-sm text-muted-foreground">{s.description}</span>
                {s.examples?.length > 0 && <span className="text-xs text-muted-foreground">Exemplo: {s.examples.join(" · ")}</span>}
              </button>
            ))}
          </div>
          <p className="dob-hint"><Info size={14} /> Não sabe? Escolha o mais próximo: pode mudar ou acrescentar depois.</p>
        </div>
      )}
    </section>
  );
}

function SpecialtyManager({ ov, cat, chantierId, reload }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [custom, setCustom] = useState({ area: "arquitetura", label: "", parent: "" });
  const enabled = new Set(ov.enabled);
  const allSpecs = useMemo(() => {
    const extra = (ov.config.custom || []).map((s) => ({ ...s, custom: true }));
    return cat.areas.map((a) => ({ ...a, specialties: [...a.specialties, ...extra.filter((s) => s.area === a.key)] }));
  }, [cat, ov]);
  const norm = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const toggle = async (key, on) => {
    setBusy(true);
    const next = on ? [...ov.enabled, key] : ov.enabled.filter((k) => k !== key);
    try { await api.put(`/dossier-obra/${chantierId}/config`, { enabled: next, hidden: (ov.config.hidden || []).filter((k) => k !== key) }); await reload(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const addCustom = async (e) => {
    e.preventDefault();
    if (custom.label.trim().length < 2) return;
    try { await api.post(`/dossier-obra/${chantierId}/especialidades`, { ...custom, parent: custom.parent || null }); toast.success("Especialidade criada"); setCustom({ ...custom, label: "" }); reload(); }
    catch (err) { toast.error(errMsg(err)); }
  };
  return (
    <section className="dob-card dob-card-pad grid gap-3" data-testid="dob-specialty-manager">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h2 className="text-lg font-bold">Especialidades desta obra</h2><p className="text-sm text-muted-foreground">Ative só as aplicáveis; as restantes ficam ocultas.</p></div>
        <label className="dob-field min-w-64"><span className="sr-only">Pesquisar</span><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Pesquisar (termos técnicos ou correntes)" data-testid="dob-spec-search" /></label>
      </div>
      {allSpecs.map((a) => {
        const list = a.specialties.filter((s) => !q || norm(`${s.label} ${s.terms || ""} ${s.description || ""}`).includes(norm(q)));
        if (!list.length) return null;
        return (
          <fieldset key={a.key} className="grid gap-1">
            <legend className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1">{a.label}</legend>
            <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-1">
              {list.map((s) => (
                <label key={s.key} className="flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-muted cursor-pointer">
                  <input type="checkbox" className="mt-1" checked={enabled.has(s.key)} disabled={busy} onChange={(e) => toggle(s.key, e.target.checked)} data-testid={`dob-enable-${s.key}`} />
                  <span><span className="text-sm font-medium">{s.label}{s.custom && " (personalizada)"}</span><br /><span className="text-xs text-muted-foreground">{s.description}</span></span>
                </label>
              ))}
            </div>
          </fieldset>
        );
      })}
      <form onSubmit={addCustom} className="flex flex-wrap items-end gap-2 border-t pt-3" data-testid="dob-custom-form">
        <label className="dob-field"><span>Área</span><select value={custom.area} onChange={(e) => setCustom({ ...custom, area: e.target.value })}>{cat.areas.map((a) => <option key={a.key} value={a.key}>{a.label}</option>)}</select></label>
        <label className="dob-field"><span>Subdivisão de (opcional)</span><select value={custom.parent} onChange={(e) => setCustom({ ...custom, parent: e.target.value })}><option value="">—</option>{cat.areas.find((a) => a.key === custom.area)?.specialties.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}</select></label>
        <label className="dob-field flex-1 min-w-48"><span>Nome</span><input value={custom.label} onChange={(e) => setCustom({ ...custom, label: e.target.value })} placeholder="Ex.: Cerâmica exterior" /></label>
        <button type="submit" className="dob-ghost"><Plus size={16} /> Criar especialidade</button>
      </form>
      <p className="dob-hint"><Info size={14} /> {cat.disclaimer}</p>
    </section>
  );
}

function Locations({ ov, chantierId, reload }) {
  const [f, setF] = useState({ kind: "edificio", name: "", parent_id: "" });
  const locs = ov.config.locations || [];
  const pathOf = (id) => { const by = Object.fromEntries(locs.map((l) => [l.location_id, l])); const p = []; let c = by[id]; let g = 0; while (c && g < 6) { p.unshift(c.name); c = by[c.parent_id]; g++; } return p.join(" · "); };
  const add = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) return;
    try { await api.post(`/dossier-obra/${chantierId}/locais`, { ...f, parent_id: f.parent_id || null }); setF({ ...f, name: "" }); reload(); }
    catch (err) { toast.error(errMsg(err)); }
  };
  const remove = async (id) => { try { await api.delete(`/dossier-obra/${chantierId}/locais/${id}`); reload(); } catch (err) { toast.error(errMsg(err)); } };
  return (
    <section className="dob-card dob-card-pad grid gap-3" data-testid="dob-locations">
      <h2 className="text-lg font-bold flex items-center gap-2"><MapPin size={18} /> Locais da obra</h2>
      <p className="text-sm text-muted-foreground">Edifício → piso → divisão ou zona. Usado para filtrar e compilar.</p>
      {locs.length === 0 ? <p className="text-sm text-muted-foreground">Ainda sem locais. A obra toda é o local por defeito.</p> :
        <ul className="grid gap-1">{locs.map((l) => <li key={l.location_id} className="flex items-center gap-2 text-sm"><Pill s="rascunho">{{ edificio: "Edifício", piso: "Piso", zona: "Zona" }[l.kind]}</Pill><span className="flex-1">{pathOf(l.location_id)}</span><button type="button" className="text-xs text-muted-foreground hover:underline" onClick={() => remove(l.location_id)}>Retirar</button></li>)}</ul>}
      <form onSubmit={add} className="flex flex-wrap items-end gap-2">
        <label className="dob-field"><span>Tipo</span><select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="edificio">Edifício</option><option value="piso">Piso</option><option value="zona">Divisão ou zona</option></select></label>
        <label className="dob-field"><span>Dentro de</span><select value={f.parent_id} onChange={(e) => setF({ ...f, parent_id: e.target.value })}><option value="">—</option>{locs.map((l) => <option key={l.location_id} value={l.location_id}>{pathOf(l.location_id)}</option>)}</select></label>
        <label className="dob-field flex-1 min-w-40"><span>Nome</span><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Ex.: Piso 1, Fachada norte" /></label>
        <button type="submit" className="dob-ghost"><Plus size={16} /> Adicionar local</button>
      </form>
    </section>
  );
}

function Dependencies({ chantierId, reloadKey }) {
  const [d, setD] = useState(null);
  const load = () => api.get(`/dossier-obra/${chantierId}/dependencias`).then(({ data }) => setD(data)).catch(() => setD(null));
  useEffect(() => { load(); }, [chantierId, reloadKey]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return null;
  const add = async (s) => { try { await api.post(`/dossier-obra/${chantierId}/dependencias`, { ...s, confirm: false }); load(); } catch (e) { toast.error(errMsg(e)); } };
  const confirm = async (id) => { try { await api.post(`/dossier-obra/${chantierId}/dependencias/${id}/confirmar`); toast.success("Sequência confirmada"); load(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <section className="dob-card dob-card-pad grid gap-2" data-testid="dob-dependencies">
      <h2 className="text-lg font-bold flex items-center gap-2"><Link2 size={18} /> Dependências entre especialidades</h2>
      {d.dependencies.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma dependência registada.</p>}
      <div className="dob-rows">
        {d.dependencies.map((x) => (
          <div key={x.dep_id} className="dob-row">
            <div className="dob-row-main"><p>{x.from_label} — {x.relation_label.toLowerCase()} — {x.to_label}</p>{x.note && <p>{x.note}</p>}</div>
            {x.status === "confirmada" ? <Pill s="confirmado">Confirmada</Pill> : <button type="button" className="dob-ghost" onClick={() => confirm(x.dep_id)} data-testid={`dob-dep-confirm-${x.dep_id}`}><Check size={15} /> Confirmar</button>}
          </div>
        ))}
      </div>
      {d.suggestions.length > 0 && (
        <details className="mt-1"><summary className="cursor-pointer text-sm font-semibold">Sequências típicas sugeridas ({d.suggestions.length})</summary>
          <div className="dob-rows mt-2">{d.suggestions.map((s, i) => (
            <div key={i} className="dob-row"><div className="dob-row-main"><p>{s.from_label} — {s.relation_label.toLowerCase()} — {s.to_label}</p><p>{s.note}</p></div>
              <button type="button" className="dob-ghost" onClick={() => add(s)}><Plus size={15} /> Propor</button></div>))}</div>
        </details>
      )}
      <p className="dob-hint"><Info size={14} /> {d.note}</p>
    </section>
  );
}

function PorOrganizar({ ov, chantierId, reload, specs }) {
  const [choice, setChoice] = useState({});
  if (!ov.por_organizar.total) return null;
  const KIND = { plan: "Planta", document: "Orçamento/fatura", plans_pro: "Análise Pro", site_report: "Relatório de obra", btp_problem: "Diagnóstico" };
  const classify = async (x) => {
    const sp = choice[x.kind + x.id];
    if (!sp) { toast.error("Escolha a especialidade"); return; }
    try { await api.post(`/dossier-obra/${chantierId}/classificar`, { kind: x.kind, id: x.id, specialty: sp }); toast.success("Classificado (o original não foi alterado)"); reload(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <section className="dob-card dob-card-pad grid gap-2" data-testid="dob-por-organizar">
      <h2 className="text-lg font-bold flex items-center gap-2"><Inbox size={18} /> Por organizar <Pill s="pendente">{ov.por_organizar.total}</Pill></h2>
      <p className="text-sm text-muted-foreground">Registos já ligados a esta obra, ainda sem especialidade. Nada foi movido nem apagado: classificar cria apenas uma referência.</p>
      <div className="dob-rows">
        {ov.por_organizar.items.map((x) => (
          <div key={x.kind + x.id} className="dob-row flex-wrap">
            <div className="dob-row-main"><p>{x.label}</p><p>{KIND[x.kind]}{x.created_at ? ` · ${String(x.created_at).slice(0, 10)}` : ""}</p></div>
            <select className="dob-select" aria-label={`Especialidade para ${x.label}`} value={choice[x.kind + x.id] || ""} onChange={(e) => setChoice({ ...choice, [x.kind + x.id]: e.target.value })}>
              <option value="">Especialidade…</option>{specs.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
            <button type="button" className="dob-ghost" onClick={() => classify(x)}>Classificar</button>
          </div>
        ))}
      </div>
    </section>
  );
}

export function Overview({ ov, cat, mode, reload }) {
  const { chantierId, base, qs, tool } = useDossierContext();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const manage = params.get("vista") === "especialidades";
  const specs = cat.areas.flatMap((a) => a.specialties).concat(ov.config.custom || []);
  const setPhase = async (p) => { try { await api.put(`/dossier-obra/${chantierId}/config`, { global_phase: p }); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const setMid = async (v) => { try { await api.put(`/dossier-obra/${chantierId}/config`, { started_mid_way: v }); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const start = async (key) => {
    try { await api.put(`/dossier-obra/${chantierId}/config`, { enabled: [...new Set([...ov.enabled, key])] }); }
    catch (e) { toast.error(errMsg(e)); return; }
    nav(`${base}/especialidade/${key}${qs()}`);
  };
  const na = ov.next_action;
  return (
    <div className="grid gap-4" data-testid="dob-overview">
      <Header ov={ov} base={base} qs={qs} />
      <section className="dob-card dob-card-pad grid gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="dob-select"><CalendarRange size={18} aria-hidden="true" /><span className="text-sm text-muted-foreground">Fase global</span>
            <select value={ov.config.global_phase || ""} onChange={(e) => setPhase(e.target.value)} data-testid="dob-global-phase"><option value="">Não definida</option>{cat.phases.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}</select>
          </label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!ov.config.started_mid_way} onChange={(e) => setMid(e.target.checked)} data-testid="dob-mid-way" /> Obra já em execução (registar só a partir de agora)</label>
        </div>
        <div className="dob-next" data-testid="dob-next-action">
          <Target size={26} className="text-[var(--dob-green)] shrink-0" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="font-bold">Próxima ação</p>
            <p className="text-sm">{na ? `${na.label}${na.specialty_label ? ` — ${na.specialty_label}` : ""}` : "Sem ações em aberto. Escolha uma especialidade para começar."}</p>
          </div>
          {na?.specialty && <Link to={`${base}/especialidade/${na.specialty}${qs()}`} className="dob-ghost">Abrir <ArrowRight size={15} /></Link>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to={tool("/planning")} className="dob-ghost"><CalendarRange size={16} /> Planeamento</Link>
          <Link to={`/chantiers/${chantierId}?tab=documents`} className="dob-ghost"><FileText size={16} /> Documentos</Link>
          <Link to={`/chantiers/${chantierId}`} className="dob-ghost"><HardHat size={16} /> Processo (orçamentos, faturas, receção)</Link>
        </div>
      </section>

      {(mode === "guiado" && !manage) ? <GuidedStart ov={ov} cat={cat} onStart={start} /> : <SpecialtyManager ov={ov} cat={cat} chantierId={chantierId} reload={reload} />}

      {ov.areas.some((a) => a.specialties.length) && (
        <section className="dob-card dob-card-pad grid gap-3" data-testid="dob-areas">
          <h2 className="text-lg font-bold">Áreas e especialidades ativas</h2>
          <div className="dob-area-grid">
            {ov.areas.filter((a) => a.specialties.length).map((a) => (
              <div key={a.key} className="dob-area-card">
                <p className="font-bold">{a.label}</p>
                <ul className="grid gap-1">{a.specialties.map((s) => (
                  <li key={s.key}><Link to={`${base}/especialidade/${s.key}${qs()}`} className="flex items-center gap-2 text-sm hover:underline"><ModuleIcon k={s.key} area={s.area} size={11} tile={20} />
                    <span className="flex-1">{s.label}</span><Pill s={s.state?.status || "por_iniciar"} />{s.counts.pending > 0 && <Pill s="pendente">{s.counts.pending} pend.</Pill>}
                  </Link></li>))}</ul>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="dob-card dob-card-pad grid gap-2" data-testid="dob-pendencias">
        <h2 className="text-lg font-bold flex items-center gap-2"><AlertTriangle size={18} /> Pendências <Pill s={ov.pendencias_total ? "pendente" : "validado"}>{ov.pendencias_total}</Pill></h2>
        {ov.pendencias.length === 0 ? <p className="text-sm text-muted-foreground">Sem pendências registadas.</p> :
          <div className="dob-rows">{ov.pendencias.slice(0, mode === "guiado" ? 5 : 30).map((p) => (
            <Link key={p.item_id} to={`${base}/especialidade/${p.specialty}${qs()}`} className="dob-row hover:bg-muted rounded-lg">
              <div className="dob-row-main"><p>{p.title}</p><p>{p.specialty_label}</p></div><Pill s={p.status} />
            </Link>))}</div>}
      </section>

      {mode === "tecnico" && <Locations ov={ov} chantierId={chantierId} reload={reload} />}
      {mode === "tecnico" && <Dependencies chantierId={chantierId} reloadKey={ov.enabled.join(",")} />}
      <PorOrganizar ov={ov} chantierId={chantierId} reload={reload} specs={specs} />
      {ov.last_emission && <p className="dob-hint"><FileText size={14} /> Última emissão: versão {String(ov.last_emission.version).padStart(2, "0")} · {ov.last_emission.created_at.slice(0, 10)} — <Link className="underline" to={`${base}/compilar${qs()}`}>ver emissões</Link></p>}
    </div>
  );
}
