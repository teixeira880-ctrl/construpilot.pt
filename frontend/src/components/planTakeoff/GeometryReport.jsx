import { useState } from "react";
import { toast } from "sonner";
import { Brain, Loader2, ChevronDown, ChevronUp, BookOpenText, FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { runCotesJob } from "@/lib/cotesJobs";

const LVL = {
  VERT: ["Cohérent", "bg-emerald-100 text-emerald-800 border-emerald-300"],
  BLEU: ["Information", "bg-blue-100 text-blue-800 border-blue-300"],
  JAUNE: ["À vérifier", "bg-yellow-100 text-yellow-800 border-yellow-300"],
  ORANGE: ["Incohérence", "bg-orange-100 text-orange-800 border-orange-300"],
  ROUGE: ["Incohérence majeure", "bg-red-100 text-red-800 border-red-300"],
};
const cm = (m) => `${(Number(m || 0) * 100) > 0 ? "+" : ""}${(Number(m || 0) * 100).toFixed(1)} cm`;

function Anomaly({ a, onFocus }) {
  const [open, setOpen] = useState(a.niveau === "ROUGE" || a.niveau === "ORANGE");
  const [label, cls] = LVL[a.niveau] || LVL.JAUNE;
  const v = a.verification || {};
  return (
    <div className={`border rounded-sm text-[11px] ${cls}`} data-testid={`geo-anomaly-${a.numero}`}>
      <button className="w-full flex items-center justify-between gap-2 px-2 py-1.5 text-left" onClick={() => setOpen(!open)}>
        <span className="font-semibold truncate">#{a.numero} · {label} — {a.localisation}</span>
        <span className="shrink-0 flex items-center gap-1">
          {a.ecart_mm != null && <span className="num">{a.ecart_mm > 0 ? "+" : ""}{Math.round(a.ecart_mm)} mm</span>}
          {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </span>
      </button>
      {open && (
        <div className="px-2 pb-2 grid gap-1 bg-white/70 text-slate-800">
          {a.donnee_plan && <p><b>Donnée du plan :</b> {a.donnee_plan}</p>}
          {a.calcul && <p><b>Calcul ConstruPilot :</b> {a.calcul}</p>}
          {a.formule && <p className="num"><b>Formule :</b> {a.formule}{a.resultat ? ` = ${a.resultat}` : ""}</p>}
          {a.explication && <p><b>Explication :</b> {a.explication}</p>}
          {a.hypotheses?.length > 0 && <p><b>Hypothèses :</b> {a.hypotheses.join(" · ")}</p>}
          {a.action && <p><b>Action recommandée :</b> {a.action}</p>}
          <p className="text-muted-foreground">Confiance {a.confiance} · Passage 2 : {v.verdict || "—"}{v.recalcul ? ` — ${v.recalcul}` : ""}</p>
          {a.adversarial && (
            <p className={`border-l-2 pl-1.5 ${a.adversarial.verdict === "MAINTENUE" ? "border-red-400" : a.adversarial.verdict === "REJETÉE" ? "border-emerald-500" : "border-yellow-500"}`} data-testid={`geo-anomaly-${a.numero}-adversarial`}>
              <b>Contrôle adversarial : {a.adversarial.verdict}</b>{a.niveau_initial && a.niveau_initial !== a.niveau ? ` (niveau ${a.niveau_initial} → ${a.niveau})` : ""}
              {a.adversarial.attaque ? ` — attaque : ${a.adversarial.attaque}` : ""}{a.adversarial.recalcul ? ` — ${a.adversarial.recalcul}` : ""}
            </p>
          )}
          {a.cotes_index?.length > 0 && onFocus && (
            <p>Cotes : {a.cotes_index.map((i) => (
              <button key={i} className="underline mr-1" onClick={() => onFocus(i)} data-testid={`geo-anomaly-${a.numero}-cote-${i}`}>#{i}</button>
            ))}</p>
          )}
        </div>
      )}
    </div>
  );
}

function Narrative({ plan, pageIndex, geo, onUpdated }) {
  const [busy, setBusy] = useState(false);
  const [secs, setSecs] = useState(0);
  const [open, setOpen] = useState(false);
  const nar = geo?.narratif;
  const write = async () => {
    setBusy(true); setSecs(0);
    try {
      const data = await runCotesJob(`/takeoffs/${plan.plan_id}/cotes/narratif`, { page_index: pageIndex }, { onTick: setSecs });
      toast.success(`Rapport narratif rédigé : ${data.sections.length} section(s)`);
      onUpdated?.({ ...geo, narratif: data });
    } catch (e) { toast.error(e?.response?.data?.detail || e?.message || "Rédaction impossible"); }
    finally { setBusy(false); }
  };
  const pdf = async (all = false) => {
    try {
      const url0 = all ? `${process.env.REACT_APP_BACKEND_URL}/api/takeoffs/${plan.plan_id}/cotes/narratif-all.pdf`
        : `${process.env.REACT_APP_BACKEND_URL}/api/takeoffs/${plan.plan_id}/cotes/narratif.pdf?page_index=${pageIndex}`;
      const res = await fetch(url0,
        {  credentials: "include" });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Erreur serveur");
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a"); a.href = url; a.download = all ? "rapport-narratif-complet.pdf" : `rapport-narratif-p${pageIndex + 1}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(e.message); }
  };
  return (
    <div className="grid gap-1 border-t pt-2" data-testid="geo-narrative">
      <div className="flex gap-2">
        <Button size="sm" variant={nar ? "outline" : "default"} className="flex-1 justify-start gap-2 rounded-sm" disabled={busy} onClick={write} data-testid="geo-narrative-btn">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BookOpenText className="h-3.5 w-3.5" />}
          {busy ? `Rédaction IA en cours (${secs} s)…` : nar ? "Réécrire le rapport narratif" : "Rédiger le rapport narratif (une section par grande cote)"}
        </Button>
        {nar && (
          <Button size="sm" variant="outline" className="gap-1 rounded-sm" onClick={() => pdf(false)} data-testid="geo-narrative-pdf-btn">
            <FileDown className="h-3.5 w-3.5" /> PDF narratif
          </Button>
        )}
      </div>
      {nar && (plan.page_count || 1) > 1 && (
        <Button size="sm" variant="outline" className="justify-start gap-1 rounded-sm" onClick={() => pdf(true)} data-testid="geo-narrative-all-pdf-btn">
          <FileDown className="h-3.5 w-3.5" /> PDF narratif complet (toutes les pages rédigées, un seul document)
        </Button>
      )}
      {nar && (
        <div className="text-[11px] border rounded-sm p-1.5 bg-muted/40 grid gap-1" data-testid="geo-narrative-body">
          {nar.stale && <p className="text-amber-800" data-testid="geo-narrative-stale">Rapport rédigé avant la dernière analyse — réécrivez-le pour l'actualiser.</p>}
          <p className="font-medium">{nar.titre || "Rapport narratif"} · {nar.sections.length} section(s)
            <button className="underline ml-2" onClick={() => setOpen(!open)} data-testid="geo-narrative-toggle">{open ? "Réduire" : "Lire"}</button></p>
          {open && (
            <>
              <p className="text-muted-foreground">{nar.introduction}</p>
              {nar.sections.map((s) => (
                <div key={s.numero} className="border-l-2 pl-1.5" style={{ borderColor: { VERT: "#16a34a", BLEU: "#2563eb", JAUNE: "#ca8a04", ORANGE: "#ea580c", ROUGE: "#dc2626" }[s.niveau] }} data-testid={`geo-narrative-section-${s.numero}`}>
                  <p className="font-semibold">{s.numero}. {s.titre}{s.ecart_mm != null ? ` — ${s.ecart_mm > 0 ? "+" : ""}${Math.round(s.ecart_mm)} mm` : ""}</p>
                  <p className="whitespace-pre-line">{s.texte}</p>
                  {s.calcul && <p className="num font-mono">{s.calcul}</p>}
                  {s.conclusion && <p><b>Conclusion :</b> {s.conclusion}</p>}
                </div>
              ))}
              {nar.conclusion && <p><b>Conclusion générale :</b> {nar.conclusion}</p>}
            </>
          )}
        </div>
      )}
    </div>
  );
}

const STUDY_STATUS = { confirmed: "border-red-300 bg-red-50 text-red-900", probable: "border-orange-300 bg-orange-50 text-orange-900",
  to_confirm: "border-amber-300 bg-amber-50 text-amber-900", insufficient_information: "border-slate-300 bg-slate-50 text-slate-700" };
const STUDY_LABEL = { confirmed: "Incohérence confirmée", probable: "Incohérence probable", to_confirm: "À confirmer", insufficient_information: "Information insuffisante" };

export function StudiesPanel({ plan, pageIndex, study, onUpdated }) {
  const [busy, setBusy] = useState(false);
  const [secs, setSecs] = useState(0);
  const [req, setReq] = useState("");
  const [effort, setEffort] = useState("high");
  const run = async () => {
    setBusy(true); setSecs(0);
    try {
      const data = await runCotesJob(`/takeoffs/${plan.plan_id}/studies/analyze`, { page_index: pageIndex, request: req, effort }, { onTick: setSecs });
      toast.success(data.verified ? "Analyse OpenAI vérifiée (2 passes)" : "Analyse OpenAI terminée — anomalies bloquantes en seconde passe");
      onUpdated?.(data);
    } catch (e) { toast.error(e?.response?.data?.detail || e?.message || "Analyse impossible"); }
    finally { setBusy(false); }
  };
  const pdf = async () => {
    try {
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/takeoffs/${plan.plan_id}/studies/report.pdf?page_index=${pageIndex}`,
        {  credentials: "include" });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Erreur serveur");
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a"); a.href = url; a.download = `analyse-openai-p${pageIndex + 1}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(e.message); }
  };
  const a = study?.analysis;
  return (
    <div className="grid gap-1.5 border-t pt-2" data-testid="studies-panel">
      <p className="text-[11px] font-medium">Analyse OpenAI GPT-6 Astra — PDF original + zooms haute résolution + calculs ConstruPilot, seconde passe de contrôle indépendante</p>
      <input className="h-7 text-[11px] border rounded-sm px-2 bg-background" placeholder="Périmètre demandé (ex. : murs et semelles du vide sanitaire, page 1)" value={req} onChange={(e) => setReq(e.target.value)} data-testid="studies-request-input" />
      <div className="flex gap-2">
        <select className="h-7 text-[11px] border rounded-sm px-1 bg-background" value={effort} onChange={(e) => setEffort(e.target.value)} data-testid="studies-effort-select">
          <option value="high">Raisonnement élevé</option>
          <option value="max">Raisonnement maximal (plan difficile)</option>
        </select>
        <Button size="sm" className="flex-1 justify-start gap-2 rounded-sm" disabled={busy} onClick={run} data-testid="studies-run-btn">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Brain className="h-3.5 w-3.5" />}
          {busy ? `Analyse OpenAI en cours (${secs} s)…` : a ? "Relancer l'analyse OpenAI" : "Lancer l'analyse OpenAI (2 passes)"}
        </Button>
        {a && <Button size="sm" variant="outline" className="gap-1 rounded-sm" onClick={pdf} data-testid="studies-pdf-btn"><FileDown className="h-3.5 w-3.5" /> PDF</Button>}
      </div>
      {a && (
        <div className="text-[11px] grid gap-1" data-testid="studies-body">
          <p className={`px-1.5 py-1 rounded-sm border ${study.verified ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-red-300 bg-red-50 text-red-900"}`} data-testid="studies-verified">
            <b>{study.verified ? "Vérifié" : "Non vérifié"}</b> · {a.inconsistencies?.length || 0} incohérence(s) · confiance {Math.round((a.global_confidence || 0) * 100)} % · {study.model}
          </p>
          {study.interior && (
            <p className={`px-1.5 py-1 rounded-sm border ${study.interior.complete ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-orange-300 bg-orange-50 text-orange-900"}`} data-testid="studies-interior">
              <b>Dimensions intérieures mur à mur (3 passes)</b> : {study.interior.complete ? "établies et fermées" : study.interior.message}
              {!study.interior.complete && study.interior.reasons?.length > 0 && <> — {study.interior.reasons.slice(0, 3).join(" ; ")}</>}
              {study.interior.ai?.summary && <span className="block text-muted-foreground mt-0.5">{study.interior.ai.summary}</span>}
            </p>
          )}
          <p className="text-muted-foreground">{a.report_summary}</p>
          {(a.inconsistencies || []).map((x) => (
            <div key={x.id} className={`px-1.5 py-1 rounded-sm border ${STUDY_STATUS[x.status] || ""}`} data-testid={`studies-inc-${x.id}`}>
              <b>{x.id} · {STUDY_LABEL[x.status] || x.status}</b> · p.{x.page ?? "—"} · {x.zone} — {x.explanation}
              {x.difference != null && <> · écart <b>{x.difference} {x.unit}</b></>}
            </div>
          ))}
          {study.verification?.summary && <p className="text-muted-foreground"><b>Seconde passe :</b> {study.verification.summary}</p>}
        </div>
      )}
    </div>
  );
}

export default function GeometryReport({ plan, pageIndex, geo, onUpdated, onFocusIndex }) {
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(true);
  const [secs, setSecs] = useState(0);
  const run = async () => {
    setBusy(true);
    setSecs(0);
    try {
      const data = await runCotesJob(`/takeoffs/${plan.plan_id}/cotes/geometry`, { page_index: pageIndex }, { onTick: setSecs });
      toast.success(`Analyse géométrique : ${LVL[data.niveau_global][0]} — ${data.anomalies.length} anomalie(s), passage 2 : ${data.double_lecture.confirmees} confirmée(s)`, { duration: 8000 });
      onUpdated?.(data);
    } catch (e) { toast.error(e?.response?.data?.detail || e?.message || "Analyse géométrique impossible"); }
    finally { setBusy(false); }
  };
  const [gl, gcls] = geo ? (LVL[geo.niveau_global] || LVL.JAUNE) : [];
  return (
    <div className="grid gap-2 border-t pt-2" data-testid="geo-report">
      <Button size="sm" variant={geo ? "outline" : "default"} className="w-full justify-start gap-2 rounded-sm" disabled={busy} onClick={run} data-testid="geo-run-btn">
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Brain className="h-3.5 w-3.5" />}
        {busy ? `Double lecture IA en cours (${secs} s)…` : geo ? "Relancer l'analyse géométrique" : "Analyse géométrique complète (double lecture IA)"}
      </Button>
      {!geo && <p className="text-[11px] text-muted-foreground">Reconstruction géométrique : fermeture des chaînes (espaces + murs), contrôles croisés, façades opposées, alignements, hypothèses de correction, matrice de cohérence — deux passes indépendantes.</p>}
      {geo && (
        <div className="grid gap-2">
          <div className="flex items-center justify-between gap-2">
            <span className={`text-[11px] font-bold px-2 py-0.5 rounded-sm border ${gcls}`} data-testid="geo-level">{gl}</span>
            <span className="text-[11px] text-muted-foreground">{geo.anomalies.length} anomalie(s) · {geo.double_lecture?.confirmees ?? 0} confirmée(s) / {geo.double_lecture?.infirmees ?? 0} infirmée(s)
              {geo.adversarial?.ok && ` · adversarial : ${geo.adversarial.maintenues} maintenue(s), ${geo.adversarial.contestees} contestée(s), ${geo.adversarial.rejetees} rejetée(s)`}</span>
            <button className="text-[11px] underline" onClick={() => setShow(!show)} data-testid="geo-toggle">{show ? "Réduire" : "Détails"}</button>
          </div>
          {geo.stale && (
            <p className="text-[11px] border border-amber-400 bg-amber-50 text-amber-900 rounded-sm px-1.5 py-1" data-testid="geo-stale">
              Les cotes ont été relues depuis cette analyse géométrique : les numéros de cotes peuvent avoir changé. Relancez l'analyse pour la mettre à jour.
            </p>
          )}
          {show && (
            <>
              {geo.document && Object.values(geo.document).some(Boolean) && (
                <p className="text-[11px] text-muted-foreground" data-testid="geo-document">
                  <b>Cartouche :</b> {Object.entries(geo.document).filter(([, v]) => v).map(([k, v]) => `${k.replace("_", " ")} : ${v}`).join(" · ")}
                </p>
              )}
              {geo.reponses && (
                <div className="text-[11px] grid gap-0.5 border rounded-sm p-1.5 bg-muted/40" data-testid="geo-answers">
                  <p><b>1. Fermeture :</b> {geo.reponses.fermeture || "NON INDIQUÉ"}</p>
                  <p><b>2. Compatibilité :</b> {geo.reponses.compatibilite || "NON INDIQUÉ"}</p>
                  <p><b>3. À vérifier :</b> {(geo.reponses.a_verifier || []).join(" ; ") || "—"}</p>
                </div>
              )}
              {geo.fermetures?.length > 0 && (
                <div className="grid gap-1" data-testid="geo-closures">
                  <p className="text-[11px] font-medium">Fermeture des chaînes</p>
                  {geo.fermetures.map((f, i) => (
                    <div key={i} className="text-[11px] border rounded-sm px-1.5 py-1 num">
                      <b>{f.direction}</b> {f.chaine} = {Number(f.cote_calculee_m).toFixed(2)} vs plan {Number(f.cote_plan_m).toFixed(2)} → <b>{cm(f.erreur_m)}</b> · {f.statut}
                    </div>
                  ))}
                </div>
              )}
              {geo.matrice?.length > 0 && (
                <div className="border rounded-sm overflow-auto" data-testid="geo-matrix">
                  <table className="w-full text-[11px]">
                    <thead className="bg-muted"><tr><th className="px-1 text-left">Élément</th><th className="px-1 text-right">Plan</th><th className="px-1 text-right">Calculé</th><th className="px-1 text-right">Écart</th><th className="px-1 text-left">Statut</th></tr></thead>
                    <tbody>{geo.matrice.map((m, i) => (
                      <tr key={i} className="border-t whitespace-nowrap"><td className="px-1 truncate max-w-[120px]" title={m.source_calcul}>{m.element}</td>
                        <td className="px-1 text-right num">{Number(m.valeur_plan_m).toFixed(2)}</td><td className="px-1 text-right num">{Number(m.valeur_calculee_m).toFixed(2)}</td>
                        <td className="px-1 text-right num">{cm(m.ecart_m)}</td><td className="px-1">{m.statut}</td></tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
              <div className="grid gap-1" data-testid="geo-anomalies">
                <p className="text-[11px] font-medium">Anomalies ({geo.anomalies.length})</p>
                {geo.anomalies.length === 0 && <p className="text-[11px] text-muted-foreground">Aucune anomalie géométrique détectée.</p>}
                {geo.anomalies.map((a) => <Anomaly key={a.numero} a={a} onFocus={onFocusIndex} />)}
              </div>
              {geo.synthese && <p className="text-[11px] text-muted-foreground" data-testid="geo-synthesis">{geo.synthese}</p>}
              {geo.double_lecture?.conclusion && <p className="text-[11px] text-muted-foreground"><b>Passage 2 :</b> {geo.double_lecture.conclusion}</p>}
            </>
          )}
          <Narrative plan={plan} pageIndex={pageIndex} geo={geo} onUpdated={onUpdated} />
        </div>
      )}
    </div>
  );
}
