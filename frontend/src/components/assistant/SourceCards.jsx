import { ExternalLink, ShieldAlert, ShieldCheck } from "lucide-react";

export const VerifiedSourceCard = ({ r }) => (
  <div className="mt-1 grid gap-1" data-testid="assistant-source-card">
    <div className="flex items-center gap-1 flex-wrap">
      {r.verified ? <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" /> : <ShieldAlert className="h-3.5 w-3.5 text-amber-600" />}
      <a href={r.url} target="_blank" rel="noreferrer" className="underline font-semibold" data-testid="assistant-source-link">{r.title || r.url} <ExternalLink className="inline h-3 w-3" /></a>
      <span className="text-muted-foreground">· {r.entity}{r.version ? ` · version ${r.version}` : ""}{r.dates_found?.[0] ? ` · ${r.dates_found[0]}` : ""}{r.pages ? ` · ${r.pages} p.` : ""}</span>
    </div>
    <div data-testid="assistant-source-status">{r.verified ? "Passage probant trouvé" : r.ok ? "Consultée — aucun passage ne soutient l'affirmation" : `Non vérifiée — ${r.error}`}{r.injection_suspected && " · texte suspect ignoré"}</div>
    {r.excerpt && <blockquote className="border-l-2 border-sky-400 pl-2 italic text-muted-foreground" data-testid="assistant-source-excerpt">« {r.excerpt.slice(0, 420)}{r.excerpt.length > 420 ? "…" : ""} »</blockquote>}
    <div className="text-muted-foreground">Consultée le {new Date(r.consulted_at).toLocaleString()} · affirmation : {r.claim}</div>
  </div>
);

export const ProductSearchCard = ({ r }) => (
  <div className="mt-1 grid gap-1" data-testid="assistant-product-search-card">
    <div>Requête envoyée (sans données privées) : <i>{r.query_used}</i>{r.country ? ` · ${r.country}` : ""}</div>
    {r.error && <div className="text-red-700">{r.error}</div>}
    {r.candidates?.length > 0 && <ul className="list-disc pl-4">{r.candidates.slice(0, 8).map((c, i) => <li key={i}><a className="underline" href={c.url} target="_blank" rel="noreferrer" data-testid={`assistant-product-candidate-${i}`}>{c.title}</a></li>)}</ul>}
    {r.next_step && <div className="text-muted-foreground">{r.next_step}</div>}
  </div>
);

const SUIT = { "adaptée": "bg-emerald-500/10 border-emerald-500/40", "adaptée sous conditions": "bg-amber-500/10 border-amber-500/40", "non adaptée": "bg-red-500/10 border-red-500/40" };

export const OptionsCompareCard = ({ r }) => (
  <div className="mt-1 grid gap-1.5" data-testid="assistant-options-card">
    <div><b>{r.decision === "recommended" ? `Recommandation : ${r.recommended_option}` : "Options conditionnelles — donnée décisive manquante"}</b></div>
    {r.missing_decisive_data?.length > 0 && <div>À préciser : {r.missing_decisive_data.join(" · ")}</div>}
    <div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="text-left border-b"><th className="pr-2">Option</th><th className="pr-2">Adéquation</th><th className="pr-2">Conditions</th><th className="pr-2">Sources</th></tr></thead>
      <tbody>{r.options?.map((o, i) => <tr key={i} className={`border-b align-top ${o.name === r.recommended_option ? "font-semibold" : ""}`} data-testid={`assistant-option-${i}`}>
        <td className="pr-2 py-1">{o.name}<div className="font-normal text-muted-foreground">{o.description}</div></td>
        <td className="pr-2 py-1"><span className={`rounded-sm border px-1 ${SUIT[o.suitability] || ""}`}>{o.suitability}</span><div className="text-muted-foreground">{o.evidence_level}</div></td>
        <td className="pr-2 py-1">{o.conditions?.join(" · ")}</td>
        <td className="pr-2 py-1">{o.sources?.length ? o.sources.map((s, j) => <div key={j}><a className="underline" href={s.url} target="_blank" rel="noreferrer">{s.title || s.entity || s.url}</a> <span className="text-muted-foreground">({s.status})</span></div>) : <span className="text-amber-700">aucune source</span>}</td>
      </tr>)}</tbody></table></div>
    {r.structural_validation_required && <div className="border-l-2 border-red-500 pl-2 text-red-700" data-testid="assistant-structural-notice">Validation structurelle spécifique requise avant exécution.</div>}
    {r.required_verifications?.length > 0 && <div>Vérifications : {r.required_verifications.join(" · ")}</div>}
    {r.next_action && <div>Prochaine étape : {r.next_action}</div>}
  </div>
);
