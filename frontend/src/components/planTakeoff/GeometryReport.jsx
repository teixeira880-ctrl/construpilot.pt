import { useState } from "react";
import { toast } from "sonner";
import { Brain, Loader2, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

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

export default function GeometryReport({ plan, pageIndex, geo, onUpdated, onFocusIndex }) {
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(true);
  const run = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/cotes/geometry`, { page_index: pageIndex }, { timeout: 240000 });
      toast.success(`Analyse géométrique : ${LVL[data.niveau_global][0]} — ${data.anomalies.length} anomalie(s), passage 2 : ${data.double_lecture.confirmees} confirmée(s)`, { duration: 8000 });
      onUpdated?.(data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Analyse géométrique impossible"); }
    finally { setBusy(false); }
  };
  const [gl, gcls] = geo ? (LVL[geo.niveau_global] || LVL.JAUNE) : [];
  return (
    <div className="grid gap-2 border-t pt-2" data-testid="geo-report">
      <Button size="sm" variant={geo ? "outline" : "default"} className="w-full justify-start gap-2 rounded-sm" disabled={busy} onClick={run} data-testid="geo-run-btn">
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Brain className="h-3.5 w-3.5" />}
        {busy ? "Double lecture IA en cours (≈ 30 s)…" : geo ? "Relancer l'analyse géométrique" : "Analyse géométrique complète (double lecture IA)"}
      </Button>
      {!geo && <p className="text-[11px] text-muted-foreground">Reconstruction géométrique : fermeture des chaînes (espaces + murs), contrôles croisés, façades opposées, alignements, hypothèses de correction, matrice de cohérence — deux passes indépendantes.</p>}
      {geo && (
        <div className="grid gap-2">
          <div className="flex items-center justify-between gap-2">
            <span className={`text-[11px] font-bold px-2 py-0.5 rounded-sm border ${gcls}`} data-testid="geo-level">{gl}</span>
            <span className="text-[11px] text-muted-foreground">{geo.anomalies.length} anomalie(s) · {geo.double_lecture?.confirmees ?? 0} confirmée(s) / {geo.double_lecture?.infirmees ?? 0} infirmée(s)</span>
            <button className="text-[11px] underline" onClick={() => setShow(!show)} data-testid="geo-toggle">{show ? "Réduire" : "Détails"}</button>
          </div>
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
        </div>
      )}
    </div>
  );
}
