import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { CheckCircle2, FileText, RefreshCw, AlertTriangle, Search, Download, GitCompare } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

const STATUS = { to_verify: ["à vérifier", "bg-amber-500/15 text-amber-700"], provisional: ["provisoire (hypothèse)", "bg-sky-500/15 text-sky-700"], validated: ["validé", "bg-emerald-500/15 text-emerald-700"], undetermined: ["non déterminé", "bg-red-500/15 text-red-700"], rejected: ["rejeté", "bg-muted"] };
const COLORS = { dalle: "rgba(59,130,246,.18)", mur: "rgba(16,185,129,.0)", ouverture: "rgba(245,158,11,.5)" };
const err = (e) => e?.response?.data?.detail || "Action impossible";

function Proof({ q, el, planId, onChanged, level }) {
  const [h, setH] = useState(""); const [th, setTh] = useState(""); const [reason, setReason] = useState(""); const [override, setOverride] = useState("");
  const assume = async () => { try { await api.put(`/btp-ai/plans/${planId}/elements/${q.element_id}/assumptions`, { hauteur_m: h ? Number(h) : null, epaisseur_m: th ? Number(th) : null, reason }); toast.success("Hypothèse déclarée — lignes dépendantes recalculées (provisoires)"); onChanged(); } catch (e) { toast.error(err(e)); } };
  const review = async (status) => { try { await api.put(`/btp-ai/plans/${planId}/quantities/${q.quantity_id}`, { status, quantity_override: override ? Number(override) : null, comment: reason }); toast.success(status === "validated" ? "Quantité validée" : "Statut mis à jour"); onChanged(); } catch (e) { toast.error(err(e)); } };
  return <div className="surface p-3 text-xs space-y-2" data-testid="btp-proof">
    <p className="font-semibold text-sm">{q.designation}</p>
    <p><strong>Formule :</strong> {q.formula} <span className="text-muted-foreground">· {q.rule_version}</span></p>
    <div><strong>Données :</strong><ul className="ml-4 list-disc">{q.inputs.map((i, k) => <li key={k}>{i.name} = <span className="num">{i.value ?? "manquant"}</span> {i.unit} — <em>{i.source}</em>{i.detail ? ` (${i.detail})` : ""}</li>)}</ul></div>
    {q.deductions.length > 0 && <div><strong>Déductions :</strong><ul className="ml-4 list-disc">{q.deductions.map((d, k) => <li key={k}>{d.name} : −<span className="num">{d.value}</span> {d.unit}</li>)}</ul></div>}
    {q.assumptions.length > 0 && <div className="text-sky-700"><strong>Hypothèses visibles :</strong> {q.assumptions.map((a) => `${a.name} = ${a.value} ${a.unit} (${a.reason})`).join(" ; ")}</div>}
    <p><strong>Quantité nette :</strong> <span className="num">{q.quantity_net ?? "—"}</span> {q.unit} · pertes {q.waste_pct} % · à commander <span className="num">{q.quantity_to_order ?? "—"}</span> {q.unit}{q.manual_correction && <span className="text-amber-700"> · corrigée manuellement (calculée : {q.quantity_computed})</span>}</p>
    {q.note && <p className="text-amber-700 flex items-center gap-1"><AlertTriangle className="h-3 w-3" /> {q.note}</p>}
    {q.conflict && <p className="text-red-700">Conflit : valeur validée précédemment {q.conflict.previous} par {q.conflict.validated_by} ; nouvelle valeur {q.quantity_net}.</p>}
    <p className="text-muted-foreground">Statut : {STATUS[q.status]?.[0]}{q.validated_by ? ` par ${q.validated_by} le ${new Date(q.validated_at).toLocaleDateString("fr-FR")}` : ""} · preuve : page {q.page_index + 1}, {el ? `${el.label} (zone surlignée)` : "zone"}</p>
    {(el?.source === "dxf" || el?.type === "niveau") && level && <div className="flex flex-wrap gap-2 items-end border-t pt-2" data-testid="btp-level-form">
      <label>Hauteur du niveau (m)<Input className="h-8 w-28 num" value={h} onChange={(e) => setH(e.target.value)} placeholder="ex. 2.70" data-testid="btp-level-height" /></label>
      <label className="flex-1 min-w-[160px]">Motif<Input className="h-8" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="ex. hauteur lue sur la coupe AA" /></label>
      <Button size="sm" variant="outline" disabled={!h} onClick={async () => { try { await api.put(`/btp-ai/plans/${planId}/elements/${level.element_id}/assumptions`, { hauteur_m: Number(h), reason }); toast.success("Hauteur du niveau déclarée — volumes DXF recalculés (provisoires)"); onChanged(); } catch (e) { toast.error(err(e)); } }} data-testid="btp-level-save">Déclarer la hauteur du niveau</Button></div>}
    {el?.type === "mur" && el?.source !== "dxf" && <div className="flex flex-wrap gap-2 items-end border-t pt-2">
      <label>Hauteur (m)<Input className="h-8 w-24 num" value={h} onChange={(e) => setH(e.target.value)} placeholder={el.dimensions.hauteur_m.value ?? "?"} data-testid="btp-assume-height" /></label>
      <label>Épaisseur (m)<Input className="h-8 w-24 num" value={th} onChange={(e) => setTh(e.target.value)} placeholder={el.dimensions.epaisseur_m.value ?? "?"} data-testid="btp-assume-thickness" /></label>
      <label className="flex-1 min-w-[160px]">Motif<Input className="h-8" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="ex. bloc 20 cm supposé" /></label>
      <Button size="sm" variant="outline" onClick={assume} disabled={!h && !th} data-testid="btp-assume-save">Déclarer l'hypothèse</Button></div>}
    <div className="flex flex-wrap gap-2 items-end border-t pt-2">
      <label>Corriger la quantité<Input className="h-8 w-28 num" value={override} onChange={(e) => setOverride(e.target.value)} placeholder={q.quantity_net ?? ""} data-testid="btp-override" /></label>
      <Button size="sm" onClick={() => review("validated")} data-testid="btp-validate"><CheckCircle2 className="h-4 w-4" /> Valider</Button>
      <Button size="sm" variant="ghost" onClick={() => review("rejected")} data-testid="btp-reject">Rejeter</Button>
      {q.status !== "to_verify" && <Button size="sm" variant="ghost" onClick={() => review("to_verify")}>Remettre à vérifier</Button>}
    </div>
  </div>;
}

function Revisions({ planId, client }) {
  const [revs, setRevs] = useState([]); const [a, setA] = useState(""); const [b, setB] = useState(""); const [diff, setDiff] = useState(null); const [busy, setBusy] = useState(false);
  useEffect(() => { api.get(`/btp-ai/plans/${planId}/revisions`).then((r) => { setRevs(r.data.revisions); if (r.data.revisions[1]) { setA(r.data.revisions[1].revision); setB(r.data.revisions[0].revision); } }).catch(() => {}); }, [planId]);
  const run = async () => { try { const r = await api.get(`/btp-ai/plans/${planId}/revisions/diff`, { params: { a, b } }); setDiff(r.data); } catch (e) { toast.error(err(e)); } };
  const amend = async () => { setBusy(true); try { const r = await api.post(`/btp-ai/plans/${planId}/amendment-draft`, { a, b, client_name: client }); toast.success(`Brouillon d'avenant créé (${r.data.lines} écart(s), incidence ${r.data.impact_total_ht} € HT)`, { action: { label: "Ouvrir", onClick: () => window.location.assign(r.data.editor_url) } }); } catch (e) { toast.error(err(e)); } finally { setBusy(false); } };
  const fmt = (r) => `${r.revision} · ${new Date(r.at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })} · ${r.count} lignes`;
  return <details className="surface p-3 text-xs" data-testid="btp-revisions"><summary className="cursor-pointer font-semibold flex items-center gap-1"><GitCompare className="h-4 w-4" /> Révisions ({revs.length}) — écarts et incidence sur le devis</summary>
    {revs.length < 2 ? <p className="text-muted-foreground mt-2">Une seule révision enregistrée : les écarts apparaîtront après une modification du plan, de la source DXF ou d'une hypothèse.</p> : <div className="mt-2 space-y-2">
      <div className="flex flex-wrap gap-2 items-center"><select className="h-8 rounded-md border bg-background px-2" value={a} onChange={(e) => setA(e.target.value)} data-testid="btp-rev-a">{revs.map((r) => <option key={r.revision} value={r.revision}>{fmt(r)}</option>)}</select><span>→</span>
        <select className="h-8 rounded-md border bg-background px-2" value={b} onChange={(e) => setB(e.target.value)} data-testid="btp-rev-b">{revs.map((r) => <option key={r.revision} value={r.revision}>{fmt(r)}</option>)}</select>
        <Button size="sm" variant="outline" onClick={run} disabled={!a || !b || a === b} data-testid="btp-rev-compare">Comparer</Button>
        {diff && diff.changed > 0 && <Button size="sm" onClick={amend} disabled={busy} data-testid="btp-amendment"><FileText className="h-4 w-4" /> Brouillon d'avenant</Button>}</div>
      {diff && <><p data-testid="btp-diff-summary"><strong>{diff.changed}</strong> écart(s) · incidence chiffrée <strong className="num">{diff.impact_total_ht} € HT</strong> sur {diff.priced_rows} ligne(s) · {diff.unpriced_changes} écart(s) sans prix · devis liés : {diff.linked_documents.map((d) => d.number || d.doc_id).join(", ") || "aucun"}</p>
        <table className="w-full"><thead><tr className="text-left text-muted-foreground"><th>Ligne</th><th className="num">Avant</th><th className="num">Après</th><th className="num">Δ</th><th>Type</th><th className="num">Incidence HT</th></tr></thead>
          <tbody>{diff.rows.filter((r) => r.kind !== "inchangée").map((r) => <tr key={r.quantity_id} className="border-t" data-testid={`btp-diff-${r.quantity_id}`}><td className="truncate max-w-[260px]">{r.designation}</td><td className="num">{r.before ?? "—"}</td><td className="num">{r.after ?? "—"}</td><td className="num">{r.delta ?? "—"} {r.unit}</td><td>{r.kind}</td><td className="num">{r.impact_ht != null ? `${r.impact_ht} €` : (r.quote ? "prix manquant" : "non rattaché")}</td></tr>)}</tbody></table>
        <p className="text-muted-foreground">{diff.note}</p></>}
    </div>}
  </details>;
}

export default function PlanAnalysis() {
  const { planId } = useParams();
  const [data, setData] = useState(null); const [img, setImg] = useState(null); const [page, setPage] = useState(0); const [sel, setSel] = useState(null); const [busy, setBusy] = useState(false); const [client, setClient] = useState(""); const [filter, setFilter] = useState("");
  const pdf = async () => { try { const r = await api.get(`/btp-ai/plans/${planId}/report.pdf`, { responseType: "blob" }); const u = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = u; a.download = `rapport-analyse-${planId}.pdf`; a.click(); URL.revokeObjectURL(u); } catch { toast.error("Rapport indisponible"); } };
  const load = async () => { try { const r = await api.get(`/btp-ai/plans/${planId}/analysis`); setData(r.data); } catch (e) { toast.error(err(e)); } };
  useEffect(() => { load(); api.get(`/takeoffs/${planId}`).then((r) => setImg(r.data.pages || [])).catch(() => {}); }, [planId]); // eslint-disable-line react-hooks/exhaustive-deps
  const pg = img?.[page]; const W = pg?.width_px || data?.plan?.pages?.[page]?.width_px || 1200; const H = pg?.height_px || data?.plan?.pages?.[page]?.height_px || 800;
  const els = useMemo(() => (data?.elements || []).filter((e) => e.page_index === page), [data, page]);
  const q = data?.quantities?.find((x) => x.quantity_id === sel); const el = q && data.elements.find((e) => e.element_id === q.element_id);
  const draft = async () => { setBusy(true); try { const r = await api.post(`/btp-ai/plans/${planId}/quote-draft`, { client_name: client }); toast.success(`Brouillon créé : ${r.data.lines} lignes${r.data.skipped_undetermined ? ` (${r.data.skipped_undetermined} non déterminée(s) ignorée(s))` : ""}`, { action: { label: "Ouvrir", onClick: () => window.location.assign(r.data.editor_url) } }); load(); } catch (e) { toast.error(err(e)); } finally { setBusy(false); } };
  if (!data) return <div className="p-6 text-sm text-muted-foreground">Chargement…</div>;
  const lots = [...new Set(data.quantities.map((x) => x.lot))];
  return <div className="p-4 sm:p-6 space-y-4" data-testid="btp-analysis-page">
    <header className="flex flex-wrap items-center gap-2">
      <div><h1 className="text-2xl font-bold">Analyse traçable — {data.plan.filename}</h1><p className="text-xs text-muted-foreground">Révision {data.analysis.revision} · {data.analysis.elements} ouvrages · {data.analysis.lines} lignes{data.analysis.has_dxf ? " · source DXF lue" : ""} · état : <strong>{data.state}</strong> · règles {data.analysis.rules_version}</p></div>
      <div className="ml-auto flex flex-wrap gap-2 items-center"><Input className="h-9 w-44" placeholder="Client (optionnel)" value={client} onChange={(e) => setClient(e.target.value)} data-testid="btp-client" />
        <Button size="sm" variant="outline" onClick={async () => { await api.post(`/btp-ai/plans/${planId}/rebuild`); load(); }} data-testid="btp-rebuild"><RefreshCw className="h-4 w-4" /> Recalculer</Button>
        <Button size="sm" variant="outline" onClick={pdf} data-testid="btp-report-pdf"><Download className="h-4 w-4" /> Rapport PDF</Button>
        <Button size="sm" onClick={draft} disabled={busy} data-testid="btp-quote-draft"><FileText className="h-4 w-4" /> Préparer le devis</Button>
        <Link to={`/plan`} className="text-xs underline">Retour au plan</Link></div>
    </header>
    <div className="flex flex-wrap gap-2 text-xs">{Object.entries(data.stats).map(([k, v]) => <Badge key={k} className={`rounded-sm border-0 ${STATUS[k]?.[1]}`}>{v} {STATUS[k]?.[0]}</Badge>)}<span className="text-muted-foreground">{data.disclaimer}</span></div>
    {data.analysis.missing?.length > 0 && <div className="rounded-md bg-amber-500/10 p-2 text-xs space-y-0.5" data-testid="btp-missing">{data.analysis.missing.map((m, i) => <p key={i} className={m.covered_by_assumption ? "text-sky-700" : "text-amber-800"}><AlertTriangle className="inline h-3 w-3 mr-1" />{m.message}</p>)}</div>}
    {data.analysis.conflicts?.length > 0 && <div className="rounded-md bg-red-500/10 p-2 text-xs" data-testid="btp-conflicts">{data.analysis.conflicts.map((c) => <p key={c.quantity_id}>Conflit : {c.designation} validée à {c.previous} par {c.validated_by}, recalculée à {c.new}.</p>)}</div>}
    <div className="grid lg:grid-cols-[1fr_420px] gap-4">
      <div className="surface p-2">
        {data.plan.pages.length > 1 && <div className="flex gap-1 mb-2">{data.plan.pages.map((p) => <button key={p.index} onClick={() => setPage(p.index)} className={`text-xs px-2 h-7 rounded border ${page === p.index ? "bg-muted font-semibold" : ""}`}>Page {p.index + 1}{!p.calibrated && " (non calibrée)"}</button>)}</div>}
        <div className="relative w-full overflow-auto" data-testid="btp-plan-canvas">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto border rounded-sm bg-white">
            {pg?.image_png_b64 && <image href={`data:${pg.img_mime || "image/png"};base64,${pg.image_png_b64}`} width={W} height={H} />}
            {els.filter((e) => e.type !== "ouverture" && e.geometry?.points_px).map((e) => { const on = el?.element_id === e.element_id || (el && el.room_id === e.room_id && e.type === "mur" && el.type === "ouverture"); return <polygon key={e.element_id} points={e.geometry.points_px.map((p) => p.join(",")).join(" ")} fill={e.type === "dalle" ? COLORS.dalle : "none"} stroke={on ? "#dc2626" : e.type === "mur" ? "#059669" : "#2563eb"} strokeWidth={on ? 6 : 3} style={{ cursor: "pointer" }} onClick={() => { const line = data.quantities.find((x) => x.element_id === e.element_id); if (line) setSel(line.quantity_id); }} data-testid={`btp-el-${e.element_id}`} />; })}
            {els.filter((e) => e.type === "ouverture").map((e, i) => { const pts = e.evidence.points_px || []; const p0 = pts[i % pts.length] || [0, 0]; const on = el?.element_id === e.element_id; return <circle key={e.element_id} cx={p0[0]} cy={p0[1]} r={on ? 14 : 9} fill={COLORS.ouverture} stroke={on ? "#dc2626" : "#b45309"} strokeWidth={2} style={{ cursor: "pointer" }} onClick={() => { const line = data.quantities.find((x) => x.element_id === e.element_id); if (line) setSel(line.quantity_id); }} data-testid={`btp-el-${e.element_id}`} />; })}
            {els.filter((e) => e.type === "dalle").map((e) => { const pts = e.geometry.points_px; const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length, cy = pts.reduce((s, p) => s + p[1], 0) / pts.length; return <text key={e.element_id + "t"} x={cx} y={cy} textAnchor="middle" fontSize={Math.max(14, W / 60)} fill="#1e3a8a" fontWeight="700">{e.room_name}</text>; })}
          </svg>
        </div>
        <p className="text-[11px] text-muted-foreground mt-1">Bleu : dalles · vert : murs · orange : ouvertures (position indicative sur le contour). Cliquez un ouvrage ou une ligne pour voir la preuve.</p>
      </div>
      <div className="space-y-3">
        {q ? <Proof q={q} el={el} planId={planId} onChanged={load} level={data.elements.find((e) => e.type === "niveau")} /> : <p className="text-sm text-muted-foreground surface p-3">Sélectionnez une quantité pour afficher la zone source, la formule, les données et leur provenance.</p>}
        <div className="surface p-2 text-xs max-h-[60vh] overflow-y-auto" data-testid="btp-quantities">
          {data.quantities.length > 40 && <Input className="h-8 mb-1" placeholder="Filtrer les lignes (M01, poteau, dalle…)" value={filter} onChange={(e) => setFilter(e.target.value)} data-testid="btp-filter" />}
          {lots.map((lot) => <div key={lot}><p className="overline mt-2 mb-1">{lot}</p>
            {data.quantities.filter((x) => x.lot === lot && (!filter || x.designation.toLowerCase().includes(filter.toLowerCase()))).slice(0, 400).map((x) => <button key={x.quantity_id} onClick={() => { setSel(x.quantity_id); setPage(x.page_index); }} className={`w-full text-left flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/60 ${sel === x.quantity_id ? "bg-muted" : ""}`} data-testid={`btp-q-${x.quantity_id}`}>
              <span className="flex-1 truncate">{x.designation}</span><span className="num">{x.quantity_net ?? "—"} {x.unit}</span><Badge className={`rounded-sm border-0 text-[10px] ${STATUS[x.status]?.[1]}`}>{STATUS[x.status]?.[0]}</Badge></button>)}</div>)}
          {data.quantities.length === 0 && <p className="p-2 text-muted-foreground">Aucune pièce tracée/calibrée sur ce plan : tracez les pièces et calibrez la page dans l'outil Plan pour obtenir un métré traçable.</p>}
        </div>
        <Revisions planId={planId} client={client} />
        <Link to="/assistant?intent=research" className="text-xs underline flex items-center gap-1"><Search className="h-3 w-3" /> Question technique documentée (assistant, outil de recherche avec sources)</Link>
      </div>
    </div>
  </div>;
}
