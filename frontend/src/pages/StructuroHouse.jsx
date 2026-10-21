import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Building2, Calculator, FileDown, Loader2, Plus, Trash2, AlertTriangle } from "lucide-react";

const USES = [["habitacao", "Habitação"], ["garagem", "Garagem"], ["comercio", "Comércio"], ["escritorios", "Escritórios"]];
const FACADES = [["frente", "Frente"], ["tras", "Trás"], ["esquerda", "Esquerda"], ["direita", "Direita"]];
const num = (v) => (v === "" || v === null || v === undefined ? null : Number(String(v).replace(",", ".")));
const list = (txt) => String(txt || "").split(/[;\s]+/).map((x) => num(x)).filter((x) => x !== null && !Number.isNaN(x));

function Field({ label, children }) {
  return <label className="grid gap-1 text-xs"><span className="text-muted-foreground">{label}</span>{children}</label>;
}

export default function StructuroHouse() {
  const [g, setG] = useState(null);
  const [wx, setWx] = useState("");
  const [wy, setWy] = useState("");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    api.get("/structuro/house/defaults").then(({ data }) => setG(data.geometry)).catch(() => toast.error("Indisponível"));
  }, []);
  if (!g) return <div className="p-8 text-sm text-muted-foreground">A carregar…</div>;

  const set = (patch) => setG((x) => ({ ...x, ...patch }));
  const setIn = (key, patch) => setG((x) => ({ ...x, [key]: { ...x[key], ...patch } }));
  const payload = () => ({ ...g, interior_walls_x: wx ? list(wx) : g.interior_walls_x, interior_walls_y: wy ? list(wy) : g.interior_walls_y });

  const compute = async () => {
    setBusy("calc");
    try { const { data } = await api.post("/structuro/house/compute", { geometry: payload() }); setRes(data); }
    catch (e) { toast.error(e?.response?.data?.detail || "Cálculo impossível"); }
    finally { setBusy(""); }
  };
  const download = async () => {
    setBusy("pdf");
    try {
      const { data } = await api.post("/structuro/house/pdf", { geometry: payload() }, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
      window.open(url, "_blank");
    } catch { toast.error("PDF impossível"); }
    finally { setBusy(""); }
  };

  return (
    <div className="mx-auto max-w-6xl p-5 space-y-6" data-testid="structuro-house">
      <div className="flex items-start gap-3">
        <span className="h-11 w-11 rounded-lg bg-primary/10 grid place-items-center"><Building2 className="h-6 w-6 text-primary" /></span>
        <div>
          <h1 className="font-display text-2xl font-bold">Estudo estrutural de moradia</h1>
          <p className="text-sm text-muted-foreground max-w-3xl">Lajes em 2 direções, descida de cargas, alvenaria (NP EN 1996-3), sapatas, lintéis, cintas e pilaretes, muros de cave e escadas. Gera a nota de cálculo A4 e os desenhos A3 de cofragem e armaduras. Também pode pedir ao Assistente Construção com o projeto e o estudo geotécnico anexados — ele preenche estes dados por si.</p>
          <p className="text-xs text-amber-700 mt-1 flex items-center gap-1"><AlertTriangle className="h-3.5 w-3.5" /> Pré-dimensionamento a verificar e assinar por engenheiro civil. Ação sísmica (NP EN 1998-1) não verificada.</p>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="rounded-xl border border-border bg-card p-4 space-y-3">
          <h3 className="font-semibold text-sm">Geometria</h3>
          <Field label="Designação da obra"><Input value={g.name} onChange={(e) => set({ name: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Comprimento exterior (m)"><Input value={g.outer_L_m} onChange={(e) => set({ outer_L_m: num(e.target.value) })} /></Field>
            <Field label="Largura exterior (m)"><Input value={g.outer_W_m} onChange={(e) => set({ outer_W_m: num(e.target.value) })} /></Field>
            <Field label="Espessura paredes resist. (m)"><Input value={g.wall_thickness_m} onChange={(e) => set({ wall_thickness_m: num(e.target.value) })} /></Field>
            <Field label="Sistema">
              <select className="h-9 rounded-md border border-border bg-background px-2 text-sm" value={g.structure} onChange={(e) => set({ structure: e.target.value })}>
                <option value="alvenaria">Alvenaria resistente</option><option value="betao">Paredes de betão</option><option value="portico">Pórtico</option>
              </select>
            </Field>
          </div>
          <Field label="Paredes interiores resistentes ∥ largura — posições X (m, desde a esquerda)"><Input placeholder="ex.: 5,6" value={wx || g.interior_walls_x.join(" ")} onChange={(e) => setWx(e.target.value)} /></Field>
          <Field label="Paredes interiores resistentes ∥ comprimento — posições Y (m, desde a frente)"><Input placeholder="ex.: 3,9" value={wy || g.interior_walls_y.join(" ")} onChange={(e) => setWy(e.target.value)} /></Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Cobertura">
              <select className="h-9 rounded-md border border-border bg-background px-2 text-sm" value={g.roof.type} onChange={(e) => setIn("roof", { type: e.target.value })}>
                <option value="inclinada">Inclinada (telha)</option><option value="laje_plana">Laje plana</option>
              </select>
            </Field>
            <Field label="Altura cumeeira (m)"><Input value={g.roof.ridge_height_m ?? ""} onChange={(e) => setIn("roof", { ridge_height_m: num(e.target.value) })} /></Field>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-4 space-y-3">
          <h3 className="font-semibold text-sm">Pisos (de baixo para cima)</h3>
          {g.levels.map((lv, i) => (
            <div key={i} className="grid grid-cols-[1fr_80px_1fr_28px] gap-2 items-end">
              <Field label="Piso"><Input value={lv.name} onChange={(e) => set({ levels: g.levels.map((x, k) => (k === i ? { ...x, name: e.target.value } : x)) })} /></Field>
              <Field label="Pé-direito+laje"><Input value={lv.storey_height_m} onChange={(e) => set({ levels: g.levels.map((x, k) => (k === i ? { ...x, storey_height_m: num(e.target.value) } : x)) })} /></Field>
              <Field label="Utilização">
                <select className="h-9 rounded-md border border-border bg-background px-2 text-sm" value={lv.use} onChange={(e) => set({ levels: g.levels.map((x, k) => (k === i ? { ...x, use: e.target.value } : x)) })}>
                  {USES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </Field>
              <button type="button" className="h-9 text-muted-foreground hover:text-destructive" onClick={() => set({ levels: g.levels.filter((_, k) => k !== i) })}><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
          <Button size="sm" variant="outline" onClick={() => set({ levels: [...g.levels, { name: `${g.levels.length}.º piso`, storey_height_m: 2.8, use: "habitacao" }] })}><Plus className="h-3.5 w-3.5 mr-1" /> Piso</Button>
          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border">
            <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={!!g.basement.present} onChange={(e) => setIn("basement", { present: e.target.checked })} /> Cave</label>
            <Field label="Altura da cave (m)"><Input value={g.basement.height_m ?? ""} onChange={(e) => setIn("basement", { height_m: num(e.target.value) })} /></Field>
            <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={!!g.stair.present} onChange={(e) => setIn("stair", { present: e.target.checked })} /> Escada interior</label>
            <div className="grid grid-cols-2 gap-1">
              <Field label="Caixa C (m)"><Input value={g.stair.cage_length_m ?? ""} onChange={(e) => setIn("stair", { cage_length_m: num(e.target.value) })} /></Field>
              <Field label="Caixa L (m)"><Input value={g.stair.cage_width_m ?? ""} onChange={(e) => setIn("stair", { cage_width_m: num(e.target.value) })} /></Field>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-4 space-y-3">
          <h3 className="font-semibold text-sm">Solo e aberturas</h3>
          <div className="grid grid-cols-2 gap-2">
            <Field label="q_ELS do estudo geotécnico (kPa)"><Input value={g.soil.q_els_kpa ?? ""} onChange={(e) => setIn("soil", { q_els_kpa: num(e.target.value), confirmed: num(e.target.value) !== null })} /></Field>
            <Field label="φ' (°) para muros"><Input value={g.soil.phi_deg ?? ""} onChange={(e) => setIn("soil", { phi_deg: num(e.target.value) })} /></Field>
          </div>
          <p className="text-[11px] text-muted-foreground">Sem q_ELS do estudo geotécnico as sapatas não são dimensionadas (só tabela de larguras).</p>
          <div className="space-y-2 border-t border-border pt-2">
            {(g.openings || []).map((op, i) => (
              <div key={i} className="grid grid-cols-[1fr_1fr_70px_28px] gap-2 items-end">
                <Field label="Piso">
                  <select className="h-9 rounded-md border border-border bg-background px-2 text-sm" value={op.level} onChange={(e) => set({ openings: g.openings.map((x, k) => (k === i ? { ...x, level: e.target.value } : x)) })}>
                    {g.levels.map((lv) => <option key={lv.name} value={lv.name}>{lv.name}</option>)}
                  </select>
                </Field>
                <Field label="Fachada">
                  <select className="h-9 rounded-md border border-border bg-background px-2 text-sm" value={op.facade} onChange={(e) => set({ openings: g.openings.map((x, k) => (k === i ? { ...x, facade: e.target.value } : x)) })}>
                    {FACADES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                </Field>
                <Field label="Vão (m)"><Input value={op.width_m ?? ""} onChange={(e) => set({ openings: g.openings.map((x, k) => (k === i ? { ...x, width_m: num(e.target.value) } : x)) })} /></Field>
                <button type="button" className="h-9 text-muted-foreground hover:text-destructive" onClick={() => set({ openings: g.openings.filter((_, k) => k !== i) })}><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
            <Button size="sm" variant="outline" onClick={() => set({ openings: [...(g.openings || []), { level: g.levels[0]?.name, facade: "frente", width_m: 1.2, label: "" }] })}><Plus className="h-3.5 w-3.5 mr-1" /> Abertura</Button>
          </div>
        </div>
      </div>

      <div className="flex gap-2">
        <Button onClick={compute} disabled={!!busy} className="gap-2" data-testid="house-compute">{busy === "calc" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />} Calcular</Button>
        <Button variant="outline" onClick={download} disabled={!!busy} className="gap-2" data-testid="house-pdf">{busy === "pdf" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />} Dossier PDF (nota + desenhos)</Button>
      </div>

      {res && (
        <div className="grid lg:grid-cols-2 gap-4" data-testid="house-results">
          <div className="rounded-xl border border-border bg-card p-4">
            <h3 className="font-semibold text-sm mb-2">Lajes</h3>
            {res.slabs.map((s) => (
              <div key={s.name} className="text-xs mb-2">
                <p className="font-medium">{s.name} — h = {String(s.h).replace(".", ",")} m</p>
                {s.panels.map((d) => <p key={d.id} className="text-muted-foreground">{d.id}: {d.lx}×{d.ly} m · inf. {d.mesh_short.label} / {d.mesh_long.label} · L/d {d.ld.l_over_d} ≤ {d.ld.limit}</p>)}
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-border bg-card p-4 text-xs space-y-1">
            <h3 className="font-semibold text-sm mb-2">Fundações, lintéis, medições</h3>
            {Object.keys(res.footings).length ? Object.entries(res.footings).map(([k, f]) => <p key={k}>Sapata {k}: b={f.b_m} h={f.h_m} {f.transv} + {f.long} (σ={f.sigma_els_kpa} kPa)</p>)
              : <p className="text-amber-700">Sapatas não dimensionadas (sem q_ELS).</p>}
            {res.lintels.map((l) => <p key={l.rep}>{l.rep} {l.level}/{l.facade} vão {l.clear} m: {l.ok ? `${l.b}×${l.h} ${l.bot} + ${l.stirrups}` : "viga a dimensionar"}</p>)}
            <p className="font-semibold pt-2">Betão {res.quantities.concrete_m3} m³ · Aço {res.quantities.steel_kg} kg ({res.quantities.ratio_kg_m3} kg/m³)</p>
            <div className="pt-2 space-y-0.5">{res.warnings.map((w, i) => <p key={i} className="text-amber-700">• {w}</p>)}</div>
          </div>
        </div>
      )}
    </div>
  );
}
