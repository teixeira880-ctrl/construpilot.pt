import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Sparkles, Construction, Download, RotateCw, Ruler, Check, X, AlertTriangle, CircleHelp, Plus, Trash2, Package, Plane, Box } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { filenameFromResponse, saveBlob } from "@/lib/downloadName";

const Pic3D = lazy(() => import("@/components/tech/Pic3D"));

const fr = (v, nd = 2) => (v == null ? "—" : Number(v).toLocaleString("pt-PT", { maximumFractionDigits: nd }));

const MODES = [
  ["move", "Mover"],
  ["calib", "Calibrar a escala"],
  ["parcel", "Traçar o limite do estaleiro"],
  ["building", "Traçar o edifício"],
  ["access", "Colocar o acesso"],
];

const rectPoints = (cx, cy, w, h, rot) => {
  const a = (rot * Math.PI) / 180;
  const c = Math.cos(a);
  const s = Math.sin(a);
  return [[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]]
    .map(([x, y]) => `${cx + x * c - y * s},${cy + x * s + y * c}`).join(" ");
};

const OBSTACLE_COLORS = { ligne_electrique: "#FFEA00", arbre: "#00E676", batiment_existant: "#64748B", voisin: "#64748B", autre: "#64748B" };

/** Curva de carga: carga admissível (t) em função do raio (m), carga a elevar e alcance necessário. */
export function LoadChart({ crane }) {
  const pts = crane.curve || [];
  if (pts.length < 2) return null;
  const Wc = 520; const Hc = 190; const L = 38; const R = 10; const T = 10; const B = 26;
  const xmax = crane.jib_m; const ymax = Math.max(crane.cmax_t, crane.load?.t || 0) * 1.08;
  const X = (r) => L + (r / xmax) * (Wc - L - R);
  const Y = (t) => T + (1 - t / ymax) * (Hc - T - B);
  let d = `M ${X(0)} ${Y(pts[0].t)} L ${X(pts[0].r_m)} ${Y(pts[0].t)}`;
  // tracé en escalier prudent : la charge baisse dès le rayon précédent
  for (let i = 1; i < pts.length; i += 1) d += ` V ${Y(pts[i].t)} H ${X(pts[i].r_m)}`;
  const ticksX = []; for (let r = 0; r <= xmax + 1e-6; r += xmax > 40 ? 10 : 5) ticksX.push(r);
  const stepY = ymax > 6 ? 2 : 1; const ticksY = []; for (let t = 0; t <= ymax; t += stepY) ticksY.push(t);
  const load = crane.load?.t; const reach = Math.min(crane.reach_required_m, xmax);
  return (
    <svg viewBox={`0 0 ${Wc} ${Hc}`} className="w-full max-w-xl" data-testid={`pic-chart-${crane.id}`}>
      {ticksY.map((t) => <g key={`y${t}`}><line x1={L} x2={Wc - R} y1={Y(t)} y2={Y(t)} stroke="#E2E8F0" /><text x={L - 4} y={Y(t) + 3} fontSize="9" textAnchor="end" fill="#64748B">{t}</text></g>)}
      {ticksX.map((r) => <text key={`x${r}`} x={X(r)} y={Hc - B + 12} fontSize="9" textAnchor="middle" fill="#64748B">{r}</text>)}
      <text x={Wc - R} y={Hc - 3} fontSize="9" textAnchor="end" fill="#64748B">raio (m)</text>
      <text x={4} y={9} fontSize="9" fill="#64748B">carga (t)</text>
      <path d={d} fill="none" stroke="#0F5257" strokeWidth="2" />
      {load != null && <><line x1={L} x2={Wc - R} y1={Y(load)} y2={Y(load)} stroke="#FF1744" strokeDasharray="5 3" />
        <text x={Wc - R - 2} y={Y(load) - 3} fontSize="9" textAnchor="end" fill="#FF1744">carga a elevar {fr(load, 2)} t</text></>}
      <line x1={X(reach)} x2={X(reach)} y1={T} y2={Hc - B} stroke="#2563EB" strokeDasharray="5 3" />
      <text x={X(reach) - 3} y={T + 9} fontSize="9" textAnchor="end" fill="#2563EB">alcance {fr(reach, 1)} m</text>
      {crane.lift_radius_m > 0 && load != null && <circle cx={X(crane.lift_radius_m)} cy={Y(load)} r="3.5" fill="#FF1744" />}
    </svg>
  );
}

export default function PicTab({ plans }) {
  const [planId, setPlanId] = useState("");
  const [busy, setBusy] = useState(false);
  const [calcBusy, setCalcBusy] = useState(false);
  const [img, setImg] = useState(null);
  const [doc, setDoc] = useState(null);
  const [site, setSite] = useState(null);
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [stale, setStale] = useState(false);
  const [mode, setMode] = useState("move");
  const [draft, setDraft] = useState([]);
  const [calibLen, setCalibLen] = useState("");
  const [selected, setSelected] = useState(null);
  const [address, setAddress] = useState("");
  const [span, setSpan] = useState("");
  const [aerialBusy, setAerialBusy] = useState(false);
  const [aerials, setAerials] = useState([]);
  const api3d = useRef(null);
  const [photo, setPhoto] = useState(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const svgRef = useRef(null);
  const drag = useRef(null);

  const W = site?.img_w || 1;
  const H = site?.img_h || 1;
  const k = site?.m_per_px || null; // mètres par pixel
  const u = W / 100; // unité graphique

  const load = (data) => {
    setDoc(data);
    setSite(data.site);
    const init = {};
    (data.questions || []).forEach((q) => { if (q.proposed != null) init[q.key] = q.proposed; });
    setAnswers({ ...init, ...(data.answers || {}) });
    setResult(data.result || null);
    setStale(false);
    setDraft([]);
    const st = data.site || {};
    setMode(!st.m_per_px ? "calib" : !(st.parcel || []).length ? "parcel" : !(st.buildings || []).length ? "building" : "move");
  };

  useEffect(() => {
    setDoc(null); setSite(null); setResult(null); setImg(null); setSelected(null); setPhoto(null);
    if (!planId) return;
    api.get(`/pro/pic/${planId}`).then(({ data }) => load(data)).catch(() => {});
  }, [planId]);

  // image de fond : plan de masse importé ou photo aérienne IGN
  const base = site?.base || "plan";
  useEffect(() => {
    if (!planId) return;
    api.get(`/pro/pic/${planId}/image`).then(({ data }) => setImg(data.image_png_b64 || null)).catch(() => setImg(null));
  }, [planId, base, doc?.updated_at]);

  const refreshAerials = () => api.get("/pro/pic").then(({ data }) => setAerials(data.items || [])).catch(() => {});
  useEffect(() => { refreshAerials(); }, []);

  const isAerialId = planId.startsWith("aerial-");
  const makeAerial = async () => {
    if (address.trim().length < 4) return toast.error("Introduza a morada da obra");
    setAerialBusy(true);
    try {
      const { data } = await api.post("/pro/pic/aerial", { address: address.trim(), plan_id: isAerialId ? planId : null, span_m: span ? Number(span) : null });
      if (data.plan_id === planId) load(data); else setPlanId(data.plan_id);
      refreshAerials();
      toast.success(data.site?.parcel?.length ? "Vista aérea pronta — limite do estaleiro = prédio cadastral. Trace o edifício a construir."
        : "Vista aérea pronta — trace o limite do estaleiro e o edifício");
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível obter a vista aérea"); }
    finally { setAerialBusy(false); }
  };

  const analyze = async () => {
    if (!planId) return toast.error("Escolha uma planta de implantação");
    setBusy(true);
    try {
      const { data } = await api.post(`/pro/pic/${planId}/analyze`);
      load(data);
      toast.success(data.site?.parcel?.length ? "Planta de implantação analisada — verifique os contornos e valide as opções"
        : "Contornos não reconhecidos — trace à mão o limite do estaleiro e o edifício");
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível analisar"); }
    finally { setBusy(false); }
  };

  const compute = async (placed = null, nextSite = site, nextAnswers = answers) => {
    setCalcBusy(true);
    try {
      const { data } = await api.post(`/pro/pic/${planId}/compute`, {
        site: { m_per_px: nextSite.m_per_px, parcel: nextSite.parcel, buildings: nextSite.buildings, accesses: nextSite.accesses },
        answers: nextAnswers, placed: placed || [],
      });
      setSite(data.site); setResult(data.result); setStale(false); setPhoto(null);
      if (!placed) {
        if (data.result.ok) toast.success("Plano de estaleiro gerado");
        else toast.warning((data.result.missing || [])[0] || "Plano gerado — há pontos a rever");
      }
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível calcular"); }
    finally { setCalcBusy(false); }
  };

  // image d'ambiance photoréaliste : l'IA habille la vue 3D affichée (sans annotations)
  const makePhoto = async () => {
    const shot = api3d.current?.capture?.({ clean: true });
    if (!shot) return toast.error("Vista 3D indisponível");
    setPhotoBusy(true);
    try {
      const { data } = await api.post(`/pro/pic/${planId}/render`, { image_b64: shot }, { timeout: 300000 });
      setPhoto(data.image_b64);
      toast.success("Render fotorrealista pronto — será incluído no PDF");
    } catch (e) { toast.error(e?.response?.data?.detail || "Render fotorrealista indisponível"); }
    finally { setPhotoBusy(false); }
  };

  const placedOf = (els) => els.filter((e) => e.type !== "acces")
    .map((e) => ({ id: e.id, x: e.x, y: e.y, w: e.w, h: e.h, rot: e.rot }));

  const downloadPdf = async () => {
    try {
      // la vue 3D affichée est jointe au PDF
      const shot = api3d.current?.capture?.();
      if (shot) await api.post(`/pro/pic/${planId}/snapshot`, { image_b64: shot }).catch(() => {});
      const res = await api.get(`/pro/pic/${planId}/pdf`, { responseType: "blob" });
      saveBlob(res.data, filenameFromResponse(res, "Plano-de-estaleiro.pdf"));
    } catch { toast.error("Não foi possível exportar o PDF — gere primeiro o plano"); }
  };

  // ---- interactions sur le plan -------------------------------------------
  const pos = (ev) => {
    const svg = svgRef.current;
    const pt = svg.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    const p = pt.matrixTransform(svg.getScreenCTM().inverse());
    return [Math.min(Math.max(p.x, 0), W), Math.min(Math.max(p.y, 0), H)];
  };
  const norm = ([x, y]) => [x / W, y / H];

  const onClickPlan = (ev) => {
    if (mode === "move") { if (!ev.target.closest?.("[data-el]")) setSelected(null); return; }
    const p = pos(ev);
    if (mode === "access") {
      const s = { ...site, accesses: [norm(p)] };
      setSite(s); setMode("move");
      if (result) compute(placedOf(result.elements), s); else setStale(true);
      return;
    }
    if (mode === "calib" && draft.length >= 2) { setDraft([p]); return; }
    setDraft([...draft, p]);
  };

  const finishDraft = () => {
    if (draft.length < 3) return toast.error("Pelo menos 3 pontos");
    const pts = draft.map(norm);
    setSite(mode === "parcel" ? { ...site, parcel: pts } : { ...site, buildings: [pts] });
    setDraft([]); setMode("move"); setStale(true);
  };

  const applyCalib = () => {
    const len = parseFloat(String(calibLen).replace(",", "."));
    if (draft.length !== 2 || !(len > 0)) return toast.error("Clique em dois pontos e introduza a distância real");
    const d = Math.hypot(draft[1][0] - draft[0][0], draft[1][1] - draft[0][1]);
    if (d < 5) return toast.error("Pontos demasiado próximos");
    setSite({ ...site, m_per_px: len / d, reference: { p1: norm(draft[0]), p2: norm(draft[1]), length_m: len } });
    setDraft([]); setCalibLen(""); setMode("move"); setStale(true);
    toast.success("Escala calibrada");
  };

  const startDrag = (ev, d) => {
    if (mode !== "move") return;
    ev.stopPropagation();
    ev.currentTarget.setPointerCapture?.(ev.pointerId);
    drag.current = { ...d, start: pos(ev), moved: false };
    if (d.kind === "el") setSelected(d.id);
  };
  const onMove = (ev) => {
    const d = drag.current;
    if (!d) return;
    const p = pos(ev);
    d.moved = true;
    if (d.kind === "el" && k) {
      const dx = (p[0] - d.start[0]) * k;
      const dy = (p[1] - d.start[1]) * k;
      setResult((r) => ({ ...r, elements: r.elements.map((e) => (e.id === d.id ? { ...e, x: d.x0 + dx, y: d.y0 + dy } : e)) }));
    } else if (d.kind === "vertex") {
      setSite((s) => {
        if (d.target === "parcel") return { ...s, parcel: s.parcel.map((q, i) => (i === d.i ? norm(p) : q)) };
        return { ...s, buildings: s.buildings.map((b, bi) => (bi === d.b ? b.map((q, i) => (i === d.i ? norm(p) : q)) : b)) };
      });
    }
  };
  const onUp = () => {
    const d = drag.current;
    drag.current = null;
    if (!d || !d.moved) return;
    if (d.kind === "vertex") { setStale(true); return; }
    const el = result.elements.find((e) => e.id === d.id);
    if (el.type === "acces") {
      const s = { ...site, accesses: [[el.x / k / W, el.y / k / H]] };
      setSite(s); compute(placedOf(result.elements), s);
    } else compute(placedOf(result.elements));
  };

  const rotateSelected = () => {
    const els = result.elements.map((e) => (e.id === selected ? { ...e, rot: (e.rot + 90) % 180 } : e));
    setResult({ ...result, elements: els });
    compute(placedOf(els));
  };

  // ---- formulaire ---------------------------------------------------------
  const setAns = (key, val) => { setAnswers((a) => ({ ...a, [key]: val })); setStale(true); };
  const groups = useMemo(() => {
    const out = [];
    const byKey = Object.fromEntries((doc?.questions || []).map((q) => [q.key, q]));
    const visible = (q) => !q.if || (answers[q.if.key] === q.if.is && (!byKey[q.if.key] || visible(byKey[q.if.key])));
    (doc?.questions || []).forEach((q) => {
      if (!visible(q)) return;
      let g = out.find((x) => x.name === q.group);
      if (!g) { g = { name: q.group, items: [] }; out.push(g); }
      g.items.push(q);
    });
    return out;
  }, [doc, answers]);

  const field = (q) => {
    const v = answers[q.key];
    if (q.type === "bool") {
      return (
        <div className="flex gap-1" data-testid={`pic-q-${q.key}`}>
          {[[true, "Sim"], [false, "Não"]].map(([val, lab]) => (
            <button key={lab} type="button" onClick={() => setAns(q.key, val)} data-testid={`pic-q-${q.key}-${val ? "oui" : "non"}`}
              className={`px-3 h-8 rounded-sm border text-xs font-semibold ${v === val ? "bg-primary text-primary-foreground border-primary" : "border-border bg-background"}`}>{lab}</button>
          ))}
        </div>
      );
    }
    if (q.type === "loads") {
      const rows = Array.isArray(v) ? v : [];
      const upd = (i, patch) => setAns(q.key, rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
      return (
        <div className="space-y-1" data-testid="pic-q-charges">
          {rows.map((r, i) => (
            <div key={i} className="flex gap-1">
              <Input value={r.label || ""} placeholder="ex.: painel de cofragem, pré-laje" className="h-8 text-xs flex-1" data-testid={`pic-load-label-${i}`}
                onChange={(e) => upd(i, { label: e.target.value })} />
              <Input type="number" value={r.t ?? ""} placeholder="t" className="h-8 text-xs w-16" data-testid={`pic-load-t-${i}`}
                onChange={(e) => upd(i, { t: e.target.value === "" ? null : parseFloat(e.target.value) })} />
              <button type="button" onClick={() => setAns(q.key, rows.filter((_, j) => j !== i))} className="h-8 w-8 grid place-items-center rounded-sm border border-border" data-testid={`pic-load-del-${i}`} aria-label="Eliminar"><Trash2 className="h-3 w-3" /></button>
            </div>
          ))}
          <button type="button" onClick={() => setAns(q.key, [...rows, { label: "", t: null }])} data-testid="pic-load-add"
            className="h-7 px-2 rounded-sm border border-dashed border-border text-xs flex items-center gap-1"><Plus className="h-3 w-3" />Adicionar uma carga</button>
        </div>
      );
    }
    if (q.type === "select") {
      return (
        <select value={v ?? ""} onChange={(e) => setAns(q.key, e.target.value)} data-testid={`pic-q-${q.key}`}
          className="h-8 w-full rounded-sm border border-border bg-background px-2 text-xs">
          {q.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
    }
    return (
      <Input type="number" value={v ?? ""} data-testid={`pic-q-${q.key}`} className="h-8 text-xs"
        onChange={(e) => setAns(q.key, e.target.value === "" ? null : parseFloat(e.target.value))} />
    );
  };

  const px = (m) => (k ? m / k : 0);
  const cranes = result?.cranes || (result?.crane ? [result.crane] : []);
  const poly = (pts) => pts.map(([x, y]) => `${x * W},${y * H}`).join(" ");
  const sel = result?.elements?.find((e) => e.id === selected);

  return (
    <div className="space-y-5" data-testid="pic-tab">
      <div className="surface p-4 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[220px]">
          <label className="text-xs text-muted-foreground">Planta de implantação</label>
          <select value={planId} onChange={(e) => setPlanId(e.target.value)} data-testid="pic-plan-select"
            className="w-full mt-1 rounded-sm border border-border bg-background px-3 py-2 text-sm">
            <option value="">— Escolher uma planta —</option>
            {plans.map((p) => <option key={p.plan_id} value={p.plan_id}>{p.filename || p.plan_id}</option>)}
            {aerials.length > 0 && (
              <optgroup label="Vistas aéreas (por morada)">
                {aerials.map((a) => <option key={a.plan_id} value={a.plan_id}>{a.filename || a.plan_id}</option>)}
              </optgroup>
            )}
          </select>
        </div>
        <Button onClick={analyze} disabled={busy || !planId || isAerialId} className="gap-2 rounded-sm" data-testid="pic-analyze-btn">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {busy ? "A ler a planta…" : doc ? "Reler a planta de implantação" : "Analisar a planta de implantação"}
        </Button>
      </div>

      <div className="surface p-4 flex flex-wrap items-end gap-3" data-testid="pic-aerial-bar">
        <div className="flex-1 min-w-[220px]">
          <label className="text-xs text-muted-foreground">Ou partir da fotografia aérea: morada da obra</label>
          <Input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="ex.: Rua do Souto 12, 4700-328 Braga" className="mt-1" data-testid="pic-aerial-address"
            onKeyDown={(e) => { if (e.key === "Enter") makeAerial(); }} />
        </div>
        <div>
          <label className="text-xs text-muted-foreground">Largura da vista</label>
          <select value={span} onChange={(e) => setSpan(e.target.value)} data-testid="pic-aerial-span"
            className="block mt-1 h-9 rounded-sm border border-border bg-background px-2 text-sm">
            <option value="">Automática</option><option value="150">150 m</option><option value="250">250 m</option><option value="400">400 m</option><option value="600">600 m</option>
          </select>
        </div>
        <Button onClick={makeAerial} disabled={aerialBusy} variant="outline" className="gap-2 rounded-sm" data-testid="pic-aerial-btn">
          {aerialBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plane className="h-4 w-4" />}
          {aerialBusy ? "A carregar da DGT…" : isAerialId ? "Reenquadrar a vista aérea" : "Vista aérea (DGT)"}
        </Button>
      </div>

      {doc && site && (
        <div className="grid lg:grid-cols-[1fr_340px] gap-5">
          <div className="space-y-3">
            <div className="surface p-3 space-y-2" data-testid="pic-canvas">
              <div className="flex flex-wrap items-center gap-1">
                {MODES.map(([m, l]) => (
                  <button key={m} onClick={() => { setMode(m); setDraft([]); }} data-testid={`pic-mode-${m}`}
                    className={`px-2.5 h-7 rounded-sm border text-xs font-semibold ${mode === m ? "bg-primary text-primary-foreground border-primary" : "border-border"}`}>{l}</button>
                ))}
                {(mode === "parcel" || mode === "building") && (
                  <Button size="sm" onClick={finishDraft} className="h-7 rounded-sm gap-1" data-testid="pic-draft-finish"><Check className="h-3 w-3" />Concluir ({draft.length} pts)</Button>
                )}
                {mode === "calib" && (
                  <span className="flex items-center gap-1">
                    <Input value={calibLen} onChange={(e) => setCalibLen(e.target.value)} placeholder="distância real (m)" className="h-7 w-36 text-xs" data-testid="pic-calib-len" />
                    <Button size="sm" onClick={applyCalib} className="h-7 rounded-sm gap-1" data-testid="pic-calib-apply"><Ruler className="h-3 w-3" />Validar</Button>
                  </span>
                )}
                {sel && sel.type !== "acces" && sel.type !== "grue" && mode === "move" && (
                  <Button size="sm" variant="outline" onClick={rotateSelected} className="h-7 rounded-sm gap-1" data-testid="pic-rotate"><RotateCw className="h-3 w-3" />Rodar</Button>
                )}
                <span className="ml-auto text-xs text-muted-foreground" data-testid="pic-scale">
                  {k ? `Escala: 1 px = ${fr(k * 100, 2)} cm${site.reference?.length_m ? ` (cota ${fr(site.reference.length_m)} m)` : ""}` : "Escala por calibrar: clique em dois pontos de distância conhecida"}
                </span>
              </div>
              <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full rounded-sm border border-border bg-white touch-none select-none"
                style={{ cursor: mode === "move" ? "default" : "crosshair" }}
                onClick={onClickPlan} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp}>
                {img && <image href={`data:image/png;base64,${img}`} x="0" y="0" width={W} height={H} />}
                {site.parcel?.length >= 3 && <polygon points={poly(site.parcel)} fill="none" stroke="#fff" strokeWidth={u * 0.7} />}
                {site.parcel?.length >= 3 && <polygon points={poly(site.parcel)} fill="none" stroke="#FF1744" strokeWidth={u * 0.4} strokeDasharray={`${u} ${u * 0.5}`} />}
                {(site.buildings || []).map((b, i) => <polygon key={i} points={poly(b)} fill="#FFC400" fillOpacity="0.45" stroke="#0A0D14" strokeWidth={u * 0.3} />)}
                {(site.obstacles || []).map((o, i) => (
                  <g key={`o${i}`} pointerEvents="none">
                    <rect x={o.bbox[0] * W} y={o.bbox[1] * H} width={(o.bbox[2] - o.bbox[0]) * W} height={(o.bbox[3] - o.bbox[1]) * H}
                      fill={OBSTACLE_COLORS[o.type] || "#64748B"} fillOpacity="0.18" stroke={OBSTACLE_COLORS[o.type] || "#64748B"} strokeWidth={u * 0.2} strokeDasharray={`${u * 0.5} ${u * 0.4}`} />
                    <text x={o.bbox[0] * W + u * 0.4} y={o.bbox[1] * H + u * 1.3} fontSize={u * 1.05} fontWeight="700" fill="#0A0D14">{o.label}</text>
                  </g>
                ))}
                {k && (result?.elements || []).filter((e) => e.type === "grue" && e.jib_m).map((e) => (
                  <g key={`sw-${e.id}`} pointerEvents="none">
                    <circle cx={px(e.x)} cy={px(e.y)} r={px(e.jib_m)} fill="#FF1744" fillOpacity="0.08" stroke="#FF1744" strokeWidth={u * 0.35} strokeDasharray={`${u * 1.2} ${u * 0.6}`} />
                    {e.lift_radius_m > 0 && e.lift_radius_m < e.jib_m - 0.05 && (
                      <circle cx={px(e.x)} cy={px(e.y)} r={px(e.lift_radius_m)} fill="none" stroke="#00C853" strokeWidth={u * 0.35} strokeDasharray={`${u * 0.5} ${u * 0.5}`} />
                    )}
                  </g>
                ))}
                {k && (result?.elements || []).map((e) => (
                  <g key={e.id} onPointerDown={(ev) => startDrag(ev, { kind: "el", id: e.id, x0: e.x, y0: e.y })}
                    style={{ cursor: mode === "move" ? "grab" : "inherit" }} data-el="1" data-testid={`pic-el-${e.id}`}>
                    <title>{e.label}</title>
                    {e.type === "acces"
                      ? <circle cx={px(e.x)} cy={px(e.y)} r={u * 1.4} fill={e.color} stroke="#fff" strokeWidth={u * 0.2} />
                      : <polygon points={rectPoints(px(e.x), px(e.y), px(e.w), px(e.h), e.rot)} fill={e.color} fillOpacity="0.65"
                        stroke={selected === e.id ? "#0A0D14" : e.color} strokeWidth={selected === e.id ? u * 0.45 : u * 0.25} />}
                    <text x={px(e.x)} y={px(e.y) + u * 0.45} textAnchor="middle" fontSize={u * 1.2} fontWeight="700" fill="#0A0D14" stroke="#fff" strokeWidth={u * 0.25} paintOrder="stroke" pointerEvents="none">
                      {e.type === "acces" ? "A" : e.type === "grue" ? (e.id === "grue_2" ? "Grua 2" : "Grua") : e.type === "branchement" ? "" : e.label.split(" ")[0]}
                    </text>
                  </g>
                ))}
                {mode === "move" && (site.parcel || []).map((p, i) => (
                  <circle key={`p${i}`} cx={p[0] * W} cy={p[1] * H} r={u * 0.6} fill="#fff" stroke="#FF1744" strokeWidth={u * 0.2}
                    onPointerDown={(ev) => startDrag(ev, { kind: "vertex", target: "parcel", i })} style={{ cursor: "move" }} />
                ))}
                {mode === "move" && (site.buildings || []).map((b, bi) => b.map((p, i) => (
                  <circle key={`b${bi}-${i}`} cx={p[0] * W} cy={p[1] * H} r={u * 0.6} fill="#fff" stroke="#0A0D14" strokeWidth={u * 0.2}
                    onPointerDown={(ev) => startDrag(ev, { kind: "vertex", target: "building", b: bi, i })} style={{ cursor: "move" }} />
                )))}
                {draft.length > 0 && <polyline points={draft.map((p) => p.join(",")).join(" ")} fill="none" stroke="#2563EB" strokeWidth={u * 0.3} />}
                {draft.map((p, i) => <circle key={`d${i}`} cx={p[0]} cy={p[1]} r={u * 0.6} fill="#2563EB" />)}
              </svg>
              <p className="text-[11px] text-muted-foreground">
                Arraste os elementos e os vértices para ajustar: a grua é verificada de novo a cada deslocação. «Gerar de novo» volta a colocar tudo automaticamente.
                {doc.analysis?.notes ? ` ${base === "aerial" ? "" : "Leitura da planta: "}${doc.analysis.notes}` : ""}
                {doc.analysis?.source && base === "aerial" ? ` Fonte: ${doc.analysis.source}.` : ""}
                
              </p>
            </div>

            {result?.elements?.length > 0 && k && !stale && (
              <div className="surface p-3" data-testid="pic-3d-section">
                <h3 className="font-bold text-sm flex items-center gap-2 mb-2"><Box className="h-4 w-4 text-primary" />Vista aérea e vista 3D do estaleiro</h3>
                <Suspense fallback={<p className="text-xs text-muted-foreground">A carregar a vista 3D…</p>}>
                  <Pic3D image={img} site={site} result={result} onReady={(a) => { api3d.current = a; }} />
                </Suspense>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Button size="sm" onClick={makePhoto} disabled={photoBusy} className="gap-2 rounded-sm" data-testid="pic-photo-btn">
                    {photoBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                    {photoBusy ? "Render em curso (1 a 3 min)…" : photo ? "Refazer o render fotorrealista" : "Render fotorrealista (IA)"}
                  </Button>
                  <span className="text-[11px] text-muted-foreground">Escolha o ângulo na vista 3D e depois peça o render: a IA dá realismo a essa vista.</span>
                </div>
                {photo && (
                  <figure className="mt-2" data-testid="pic-photo">
                    <img src={`data:image/png;base64,${photo}`} alt="Render fotorrealista do estaleiro" className="w-full rounded-sm border border-border" />
                    <figcaption className="text-[11px] text-muted-foreground mt-1">Imagem de ambiente gerada por IA a partir da vista 3D — não contratual: só a planta e a memória fazem fé.</figcaption>
                  </figure>
                )}
              </div>
            )}

            {result && (
              <div className="space-y-3" data-testid="pic-result">
                {(result.missing || []).length > 0 && (
                  <div className="surface p-3 border-l-4 border-destructive" data-testid="pic-missing">
                    <h4 className="font-bold text-sm flex items-center gap-2"><CircleHelp className="h-4 w-4 text-destructive" />Informações a completar</h4>
                    <ul className="text-xs mt-1 list-disc pl-5 space-y-0.5">{result.missing.map((m, i) => <li key={i}>{m}</li>)}</ul>
                  </div>
                )}
                {cranes.map((crane) => (
                  <div key={crane.id} className="surface p-4 space-y-2" data-testid={`pic-crane-${crane.id}`}>
                    <div className="flex flex-wrap items-center gap-2">
                      <Construction className="h-4 w-4 text-primary" />
                      <h3 className="font-bold">{cranes.length > 1 ? `Grua ${crane.num} — ` : ""}{crane.label || "Grua a definir"}</h3>
                      {crane.label && (
                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${crane.ok ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}`} data-testid={`pic-crane-verdict-${crane.id}`}>
                          {crane.ok ? "Grua adequada" : "Grua a rever"}
                        </span>
                      )}
                    </div>
                    {crane.label && (
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                        {[["Lança", `${fr(crane.jib_m)} m`], ["Alcance necessário", `${fr(crane.reach_required_m, 1)} m`],
                          ["Carga na ponta da lança", `${fr(crane.tip_t)} t`], ["Carga no raio útil", `${fr(crane.capacity_at_reach_t)} t`],
                          ["Carga a elevar", crane.load?.t != null ? `${fr(crane.load.t, 3)} t` : "por indicar"],
                          ["Taxa de utilização", crane.usage_pct != null ? `${fr(crane.usage_pct, 1)} %` : "—"],
                          ["Altura sob o gancho", crane.hsc_required_m != null ? `${fr(crane.hsc_required_m)} m` : "por indicar"],
                          ["Raio de elevação (carga máx.)", crane.lift_radius_m != null ? `${fr(crane.lift_radius_m, 1)} m` : "—"],
                          ["Sobrevoo fora do estaleiro", `${fr(crane.survol_hors_emprise_m2, 0)} m²`]].map(([l, v]) => (
                          <div key={l} className="rounded-sm border border-border p-2"><div className="text-muted-foreground">{l}</div><div className="font-bold text-sm">{v}</div></div>
                        ))}
                      </div>
                    )}
                    {(crane.checks || []).length > 0 && (
                      <table className="w-full text-xs" data-testid={`pic-checks-${crane.id}`}>
                        <tbody>
                          {crane.checks.map((c, i) => (
                            <tr key={i} className="border-t border-border/60">
                              <td className="p-1.5 w-5">{c.ok ? <Check className="h-4 w-4 text-green-700" /> : <X className="h-4 w-4 text-red-700" />}</td>
                              <td className="p-1.5 font-semibold">{c.label}</td>
                              <td className="p-1.5 text-muted-foreground">{c.detail}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                    {crane.label && <LoadChart crane={crane} />}
                    {crane.source && <p className="text-[11px] text-muted-foreground">Fonte: {crane.source}. A confirmar com a ficha técnica da empresa de aluguer.</p>}
                    <details className="text-xs">
                      <summary className="cursor-pointer font-semibold">Outras gruas do catálogo para este alcance</summary>
                      <ul className="mt-1 space-y-0.5">
                        {(crane.alternatives || []).map((a) => (
                          <li key={a.key} className={a.ok ? "text-green-800" : "text-muted-foreground"}>
                            {a.ok ? "✓" : "✗"} {a.label}{a.jib_m ? ` — lança de ${fr(a.jib_m)} m, ${fr(a.capacity_t)} t no raio útil` : ""}{a.reasons?.length ? ` — ${a.reasons.join(" ; ")}` : ""}
                          </li>
                        ))}
                      </ul>
                    </details>
                  </div>
                ))}
                {cranes.length > 0 && (result.coverage || result.interference || (result.loads || []).length > 0) && (
                  <div className="surface p-4 space-y-2 text-xs" data-testid="pic-coverage">
                    <h3 className="font-bold text-sm">Cobertura do edifício</h3>
                    {result.coverage && (
                      <p>Sob a lança: <b>{fr(result.coverage.portee_pct, 1)} %</b>
                        {result.coverage.charge_pct != null ? <> · elevável com a carga mais pesada: <b className={result.coverage.charge_pct >= 99.5 ? "text-green-700" : "text-red-700"}>{fr(result.coverage.charge_pct, 1)} %</b> (círculo verde tracejado na planta)</> : null}</p>
                    )}
                    {result.interference && (
                      <p className={result.interference.ok ? "" : "text-red-700 font-semibold"} data-testid="pic-interference">Interferência: {result.interference.detail}.</p>
                    )}
                    {(result.loads || []).length > 0 && (
                      <table className="w-full" data-testid="pic-loads">
                        <thead><tr className="text-left text-muted-foreground"><th className="p-1">Carga</th><th className="p-1">Peso</th><th className="p-1">Raio de elevação</th><th className="p-1">Edifício coberto</th></tr></thead>
                        <tbody>
                          {result.loads.map((l, i) => (
                            <tr key={i} className="border-t border-border/60">
                              <td className="p-1">{l.label}</td><td className="p-1">{fr(l.t, 3)} t</td>
                              <td className="p-1">{l.radius_m.map((r) => `${fr(r, 1)} m`).join(" / ")}</td>
                              <td className={`p-1 font-bold ${l.ok ? "text-green-700" : "text-red-700"}`}>{fr(l.coverage_pct, 1)} %</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
                {(result.warnings || []).length > 0 && (
                  <div className="surface p-3 border-l-4 border-amber-500" data-testid="pic-warnings">
                    <h4 className="font-bold text-sm flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-amber-600" />Pontos de atenção</h4>
                    <ul className="text-xs mt-1 list-disc pl-5 space-y-0.5">{result.warnings.map((m, i) => <li key={i}>{m}</li>)}</ul>
                  </div>
                )}
                {(result.materiel || []).length > 0 && (
                  <div className="surface p-4 text-xs" data-testid="pic-materiel">
                    <h3 className="font-bold text-sm flex items-center gap-2 mb-1"><Package className="h-4 w-4 text-primary" />Material de estaleiro</h3>
                    <table className="w-full">
                      <tbody>
                        {result.materiel.map((m, i) => (
                          <tr key={i} className="border-t border-border/60">
                            <td className="p-1">{m.designation}</td>
                            <td className="p-1 font-bold text-right whitespace-nowrap">{fr(m.quantite, 1)} {m.unite}</td>
                            <td className="p-1 text-muted-foreground">{m.base}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <div className="surface p-3 text-xs space-y-2">
                  <p>Estaleiro <b>{fr(result.site?.parcel_m2, 0)} m²</b> · edifício <b>{fr(result.site?.building_m2, 0)} m²</b> · área livre <b>{fr(result.site?.free_m2, 0)} m²</b>
                    {result.cloture_ml ? <> · vedação <b>{fr(result.cloture_ml, 1)} m</b></> : null}
                    {result.base_vie ? <> · para {result.base_vie.effectif} trabalhadores: <b>pelo menos {result.base_vie.wc} retrete(s)</b> ({result.base_vie.ref}). {result.base_vie.nota}</> : null}</p>
                  {(result.hypotheses || []).length > 0 && (
                    <details><summary className="cursor-pointer font-semibold">Hipóteses adotadas</summary>
                      <ul className="mt-1 list-disc pl-5 space-y-0.5">{result.hypotheses.map((m, i) => <li key={i}>{m}</li>)}</ul></details>
                  )}
                  <details><summary className="cursor-pointer font-semibold">A fazer antes do arranque</summary>
                    <ul className="mt-1 list-disc pl-5 space-y-0.5">{(result.checklist || []).map((m, i) => <li key={i}>{m}</li>)}</ul></details>
                </div>
              </div>
            )}
          </div>

          <div className="surface p-4 space-y-3 h-fit" data-testid="pic-questions">
            <h3 className="font-bold">Opções a validar</h3>
            {groups.map((g) => (
              <div key={g.name} className="space-y-2">
                <div className="text-[10px] font-bold uppercase text-primary">{g.name}</div>
                {g.items.map((q) => (
                  <div key={q.key}>
                    <label className="text-xs text-muted-foreground block mb-0.5">{q.label}</label>
                    {field(q)}
                  </div>
                ))}
              </div>
            ))}
            <Button onClick={() => compute()} disabled={calcBusy} className="w-full gap-2 rounded-sm" data-testid="pic-compute-btn">
              {calcBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Construction className="h-4 w-4" />}
              {result ? "Gerar de novo" : "Gerar o plano de estaleiro"}
            </Button>
            {stale && result && <p className="text-[11px] text-amber-700" data-testid="pic-stale">Opções ou contornos alterados: gere o plano de novo.</p>}
            <Button variant="outline" onClick={downloadPdf} disabled={!result?.elements?.length || stale} className="w-full gap-2 rounded-sm" data-testid="pic-pdf-btn">
              <Download className="h-4 w-4" />Descarregar o PDF
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
