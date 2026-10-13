import { AlertTriangle, CheckCircle2, FileDown } from "lucide-react";
import { toast } from "sonner";

async function dlBlob(path, name) {
  const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api${path}`, {  credentials: "include" });
  if (!res.ok) return toast.error("PDF indisponible");
  const url = URL.createObjectURL(await res.blob()); const el = document.createElement("a"); el.href = url; el.download = name; el.click(); URL.revokeObjectURL(url);
}

const REF = { inside_face_to_inside_face: "nu int. → nu int.", outside_face_to_outside_face: "nu ext. → nu ext.", axis_to_axis: "axe → axe",
  axis_to_face: "axe → nu", wall_thickness: "épaisseur", cumulative: "cumulée", partial_anchor: "partielle", unresolved: "non rattachée" };
const STATUS = { confirmed: ["Confirmée", "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"], probable: ["Probable", "bg-sky-500/15 text-sky-700 dark:text-sky-400"],
  to_confirm: ["À confirmer", "bg-orange-500/15 text-orange-700 dark:text-orange-400"], unreadable: ["Illisible", "bg-red-500/15 text-red-700 dark:text-red-400"] };
const FACE = { interior_right: "face int. droite", interior_left: "face int. gauche", interior_top: "face int. haute", interior_bottom: "face int. basse" };

const SIDE = { haut: "Haut", bas: "Bas", gauche: "Gauche", droite: "Droite", intérieure: "Intérieure (axes)" };
const ST = { ok: "bg-emerald-500/15 text-emerald-700", warn: "bg-amber-500/15 text-amber-700", ko: "bg-red-500/15 text-red-700", no_total: "bg-muted text-muted-foreground", reference_shift: "bg-sky-500/15 text-sky-700" };

function PeripheralChains({ p, onFocusCote, planId, pageIndex }) {
  const inc = p.inconsistencies || [];
  return (
    <div className="grid gap-2 border rounded-sm p-3 bg-amber-500/5 border-amber-400/40" data-testid="peripheral-chains">
      <div className="flex flex-wrap items-center gap-2">
        <b className="text-sm">Chaînes de cotes périphériques (haut / bas / gauche / droite)</b>
        <span className="text-xs text-muted-foreground">{p.summary.chains} chaîne(s) · {p.summary.comparisons} comparaison(s) · <b className={inc.length ? "text-red-600" : "text-emerald-700"}>{inc.length} incohérence(s)</b></span>
        {planId && <button className="ml-auto inline-flex items-center gap-1 text-xs px-2 py-1 rounded-sm border bg-background hover:bg-muted transition-colors" onClick={() => dlBlob(`/takeoffs/${planId}/cotes/inconsistencies.pdf?page_index=${pageIndex}`, "incoherences-cotation.pdf")} data-testid="inconsistencies-pdf-btn"><FileDown className="h-3 w-3" /> Exporter en PDF (architecte)</button>}
      </div>
      <div className="grid gap-1 text-xs">
        {p.chains.map((c) => (
          <div key={c.chain_id} className="flex flex-wrap items-center gap-x-2" data-testid={`chain-${c.chain_id}`}>
            <span className="font-mono">{c.chain_id}</span><span className="font-medium">{SIDE[c.side] || c.side}</span>
            <span className="text-muted-foreground">{c.partials.map((x) => x.value_m.toFixed(2)).join(" + ")} = <b>{c.sum_m.toFixed(2)}</b></span>
            {c.total_m != null ? <span>· total écrit {c.total_m.toFixed(2)} m · écart {c.difference_mm > 0 ? "+" : ""}{Math.round(c.difference_mm)} mm</span>
              : c.reference_total_m != null ? <span>· dimension générale voisine {c.reference_total_m.toFixed(2)} m (chaîne partielle, {Math.round(c.uncovered_m * 1000)} mm non couverts)</span>
              : <span>· pas de total écrit</span>}
            <span className={`px-1.5 py-0.5 rounded-sm ${ST[c.status] || ""}`}>{{ ok: "cohérente", warn: "écart", ko: "incohérente", no_total: "sans total" }[c.status]}</span>
          </div>
        ))}
      </div>
      {inc.length > 0 && (
        <ul className="grid gap-1 text-xs" data-testid="peripheral-inconsistencies">
          {inc.map((x, i) => (
            <li key={i} className={`border-l-4 pl-2 py-0.5 cursor-pointer hover:bg-muted/60 ${x.status === "ko" ? "border-red-500" : "border-amber-500"}`} onClick={() => onFocusCote && onFocusCote(x.a_item_index || x.b_item_index)} data-testid={`peripheral-inc-${i}`}>
              <b>{x.status === "ko" ? "Incohérence" : "À vérifier"}</b> — {x.detail}
            </li>
          ))}
        </ul>
      )}
      {p.comparisons.some((c) => c.status === "reference_shift") && (
        <p className="text-[11px] text-muted-foreground">Écarts égaux à une épaisseur voisine (ex. 5,07 nu/nu ↔ 5,20 axe/axe = 0,13 m) : références différentes, considérés cohérents.</p>
      )}
    </div>
  );
}

export function InteriorPanel({ interior, selected, onSelect, aiInterior, onFocusCote, planId, pageIndex }) {
  if (!interior) return null;
  const v = interior.validation || {};
  const st = interior.stats || {};
  return (
    <section className="grid gap-3 border rounded-sm p-4 bg-card" data-testid="interior-panel">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base md:text-lg font-semibold">Dimensions intérieures mur à mur</h2>
        <span className="text-xs text-muted-foreground" data-testid="interior-stats">
          {st.walls ?? 0} contour(s) à deux faces · {st.measurements} mesure(s) · {st.confirmed} confirmée(s) · {st.rows_closed}/{st.rows} rangée(s) fermée(s)
          {interior.sections_ignored?.length > 0 && <> · sections ignorées : {interior.sections_ignored.join(", ")}</>}
        </span>
      </div>
      {v.complete
        ? <div className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400" data-testid="interior-complete"><CheckCircle2 className="h-4 w-4" /> Les {interior.coverage?.confirmed ?? 0} cellules rectangulaires détectées sont mesurées dans les deux sens et rapprochées des cotes écrites. Les rangées contrôlées se ferment sur les cotes extérieures.</div>
        : <div className="border-l-4 border-orange-500 bg-orange-500/10 px-3 py-2 text-sm" data-testid="interior-incomplete">
            <div className="flex items-center gap-2 font-medium"><AlertTriangle className="h-4 w-4 text-orange-600" /> {v.message || "Analyse incomplète"}</div>
            <ul className="list-disc ml-6 mt-1 text-xs text-muted-foreground">{(v.failed_checks || []).map((f, i) => <li key={i}>{f}</li>)}</ul>
          </div>}
      {aiInterior && (
        <p className="text-xs text-muted-foreground border-l-2 pl-2" data-testid="interior-ai-summary">
          <b>Relecture IA (3 passes)</b> — {aiInterior.complete ? "analyse complète validée" : "analyse non validée"}
          {aiInterior.ai?.summary ? ` : ${aiInterior.ai.summary}` : ""}
          {aiInterior.reasons?.length > 0 && <> · {aiInterior.reasons.slice(0, 4).join(" ; ")}</>}
        </p>
      )}
      <div className="overflow-x-auto rounded-sm border">
        <table className="w-full text-xs" data-testid="interior-table">
          <thead className="bg-muted/40 text-[10px] uppercase tracking-wide">
            <tr><th className="px-2 py-1.5 text-left">Zone</th><th className="px-2 py-1.5 text-left">Direction</th><th className="px-2 py-1.5 text-left">Mur de départ</th><th className="px-2 py-1.5 text-left">Mur d'arrivée</th><th className="px-2 py-1.5 text-left">Référence</th><th className="px-2 py-1.5 text-right">Cote lue</th><th className="px-2 py-1.5 text-right">Mesure</th><th className="px-2 py-1.5 text-right">Écart</th><th className="px-2 py-1.5 text-right">Confiance</th><th className="px-2 py-1.5">Statut</th></tr>
          </thead>
          <tbody>
            {!interior.interior_measurements?.length && <tr><td colSpan={10} className="px-2 py-3 text-muted-foreground">Aucune mesure intérieure établie. Vérifiez les faces des murs et l'échelle sur le PDF source.</td></tr>}
            {(interior.interior_measurements || []).map((m) => {
              const [lbl, cls] = STATUS[m.status] || [m.status, ""];
              const sel = selected === m.measurement_id;
              return (
                <tr key={m.measurement_id} onClick={() => onSelect(sel ? null : m.measurement_id)}
                    className={`border-t cursor-pointer transition-colors hover:bg-muted/60 ${sel ? "bg-amber-500/15" : ""}`} data-testid={`interior-row-${m.measurement_id}`}>
                  <td className="px-2 py-1 font-mono">{m.measurement_id}</td>
                  <td className="px-2 py-1">{m.direction === "horizontal" ? "horizontale" : "verticale"}</td>
                  <td className="px-2 py-1">{m.from_wall} <span className="text-muted-foreground">({FACE[m.from_face] || m.from_face})</span></td>
                  <td className="px-2 py-1">{m.to_wall} <span className="text-muted-foreground">({FACE[m.to_face] || m.to_face})</span></td>
                  <td className="px-2 py-1">{REF[m.reference_type] || m.reference_type}{m.axis_cote_m ? <span className="text-muted-foreground"> · axe/axe {m.axis_cote_m.toFixed(2)}</span> : null}</td>
                  <td className="px-2 py-1 text-right">{m.written_dimension_m != null ? `${m.written_dimension_m.toFixed(2)} m` : "—"}</td>
                  <td className="px-2 py-1 text-right font-medium">{m.geometric_dimension_m.toFixed(3)} m</td>
                  <td className={`px-2 py-1 text-right ${m.difference_m && Math.abs(m.difference_m) > 0.0105 ? "text-orange-600" : ""}`}>{m.difference_m != null ? `${Math.round(m.difference_m * 1000) > 0 ? "+" : ""}${Math.round(m.difference_m * 1000)} mm` : "—"}</td>
                  <td className="px-2 py-1 text-right">{Math.round(m.confidence * 100)} %</td>
                  <td className="px-2 py-1"><span className={`px-1.5 py-0.5 rounded-sm whitespace-nowrap ${cls}`}>{lbl}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {interior.peripheral && <PeripheralChains p={interior.peripheral} onFocusCote={onFocusCote} planId={planId} pageIndex={pageIndex} />}
      {interior.walls?.length > 0 && (
        <details className="text-xs" data-testid="interior-walls">
          <summary className="cursor-pointer font-medium">Ouvrages détectés ({interior.walls.length}) — classe indicative d'après la bibliothèque de symboles (la légende du plan reste prioritaire)</summary>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-1 mt-2">
            {interior.walls.map((w) => (
              <div key={w.wall_id} className="border rounded-sm px-2 py-1 bg-background" data-testid={`wall-${w.wall_id}`}>
                <b className="font-mono">{w.wall_id}</b> · {w.orientation === "vertical" ? "vertical" : "horizontal"} · {(w.thickness_m * 100).toFixed(1)} cm · {w.length_m.toFixed(2)} m
                <div className="text-muted-foreground">{w.ouvrage_class}{w.ambiguous ? " · ambigu" : ""}{w.labels?.length ? ` · repères : ${w.labels.slice(0, 5).join(", ")}` : ""}</div>
              </div>
            ))}
          </div>
        </details>
      )}
      {interior.closure_equations?.length > 0 && (
        <div className="grid gap-1 text-xs" data-testid="interior-closures">
          <b>Équations de fermeture</b>
          {interior.closure_equations.slice(0, 8).map((r) => (
            <div key={r.row_id} className="flex flex-wrap gap-x-2 border-l-2 pl-2" style={{ borderColor: r.status === "closed" ? "#16a34a" : r.status === "open" ? "#dc2626" : "#d97706" }}>
              <span className="font-mono">{r.row_id}</span>
              <span className="text-muted-foreground">{r.terms.map((t) => t.value_m.toFixed(2)).join(" + ")} = <b>{r.sum_m.toFixed(3)}</b></span>
              <span>· cote ext. {r.written_exterior_m != null ? `${r.written_exterior_m.toFixed(2)} m` : "non trouvée"}</span>
              {r.difference_m != null && <span>· écart {Math.round(r.difference_m * 1000)} mm</span>}
              <span className="font-medium">{{ closed: "fermée", open: "ouverte", not_compared: "non comparée" }[r.status]}</span>
            </div>
          ))}
          {interior.closure_equations.length > 8 && <span className="text-muted-foreground">… {interior.closure_equations.length - 8} autre(s) rangée(s) dans le rapport PDF</span>}
        </div>
      )}
    </section>
  );
}
