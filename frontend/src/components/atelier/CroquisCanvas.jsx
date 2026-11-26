import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pencil, Square, Minus, DoorOpen, AppWindow, PanelsTopLeft, Type, Ruler, Undo2, Trash2, Wand2, Loader2, ZoomIn, ZoomOut } from "lucide-react";
import { Button } from "@/components/ui/button";

// Croquis à main levée : souris, doigt ou stylet (Pointer Events). Les points sont envoyés en mètres (grille = 1 m par
// carreau à l'échelle de départ) ; le serveur redresse, raccorde, met à l'échelle des cotes et crée la maquette du Studio.
const OUTILS = [
  { id: "mur", icon: Pencil, couleur: "#1f2933", epaisseur: 4 },
  { id: "mur_ext", icon: Square, couleur: "#0f4c45", epaisseur: 6 },
  { id: "cloison", icon: Minus, couleur: "#52606d", epaisseur: 2.5 },
  { id: "porte", icon: DoorOpen, couleur: "#b87333", epaisseur: 5 },
  { id: "fenetre", icon: AppWindow, couleur: "#2b8cbe", epaisseur: 5 },
  { id: "baie", icon: PanelsTopLeft, couleur: "#1d6fa5", epaisseur: 6 },
  { id: "texte", icon: Type },
  { id: "cote", icon: Ruler, couleur: "#c2410c", epaisseur: 1.5 },
];

const COPY = {
  fr: {
    mur: "Mur", mur_ext: "Mur extérieur", cloison: "Cloison", porte: "Porte", fenetre: "Fenêtre", baie: "Baie vitrée", texte: "Nom de pièce",
    cote: "Cote", annuler: "Annuler", effacer: "Tout effacer", redresser: "Redresser et créer la maquette",
    aide: "Dessinez librement : les murs tremblés seront redressés et raccordés. Une porte ou une fenêtre se trace sur le mur. "
      + "Tracez une cote sur une longueur connue (ex. façade = 12 m) pour mettre tout le croquis à l'échelle. Grille : 1 carreau = 1 m.",
    nomPiece: "Nom de la pièce ?", longueur: "Longueur réelle de cette cote, en mètres ?", vide: "Dessinez au moins un mur.",
    confirmer: "Effacer tout le croquis ?",
  },
  pt: {
    mur: "Parede", mur_ext: "Parede exterior", cloison: "Divisória", porte: "Porta", fenetre: "Janela", baie: "Envidraçado", texte: "Nome da divisão",
    cote: "Cota", annuler: "Anular", effacer: "Apagar tudo", redresser: "Endireitar e criar o modelo",
    aide: "Desenhe livremente: as paredes tremidas são endireitadas e ligadas. Uma porta ou janela desenha-se sobre a parede. "
      + "Trace uma cota numa medida conhecida (ex. fachada = 12 m) para pôr todo o esboço à escala. Grelha: 1 quadrado = 1 m.",
    nomPiece: "Nome da divisão?", longueur: "Comprimento real desta cota, em metros?", vide: "Desenhe pelo menos uma parede.",
    confirmer: "Apagar todo o esboço?",
  },
  en: {
    mur: "Wall", mur_ext: "Exterior wall", cloison: "Partition", porte: "Door", fenetre: "Window", baie: "Glazed door", texte: "Room name",
    cote: "Dimension", annuler: "Undo", effacer: "Clear all", redresser: "Straighten and create the model",
    aide: "Draw freely: shaky walls are straightened and joined. Draw a door or window over its wall. Draw a dimension on a known "
      + "length (e.g. façade = 12 m) to scale the whole sketch. Grid: 1 square = 1 m.",
    nomPiece: "Room name?", longueur: "Real length of this dimension, in metres?", vide: "Draw at least one wall.",
    confirmer: "Clear the whole sketch?",
  },
};

const H = 560;

export default function CroquisCanvas({ lang = "fr", onRedresser, enCours = false }) {
  const c = COPY[lang] || COPY.fr;
  const [outil, setOutil] = useState("mur");
  const [traits, setTraits] = useState([]);
  const [textes, setTextes] = useState([]);
  const [cotes, setCotes] = useState([]);
  const [enTrace, setEnTrace] = useState(null);
  const [ppm, setPpm] = useState(36);                  // pixels par mètre (zoom)
  const [largeur, setLargeur] = useState(900);
  const histo = useRef([]);
  const svg = useRef(null);
  const boite = useRef(null);

  useEffect(() => {
    const el = boite.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => setLargeur(Math.max(320, el.clientWidth || 900)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const point = useCallback((ev) => {
    const r = svg.current.getBoundingClientRect();
    return [Math.round(((ev.clientX - r.left) / ppm) * 1000) / 1000, Math.round(((ev.clientY - r.top) / ppm) * 1000) / 1000];
  }, [ppm]);

  const memo = () => histo.current.push({ traits, textes, cotes });
  const down = (ev) => {
    if (enCours) return;
    ev.preventDefault();
    const p = point(ev);
    if (outil === "texte") {
      const nom = window.prompt(c.nomPiece);
      if (nom && nom.trim()) { memo(); setTextes((t) => [...t, { x: p[0], y: p[1], nom: nom.trim().slice(0, 40) }]); }
      return;
    }
    svg.current.setPointerCapture?.(ev.pointerId);
    setEnTrace({ type: outil, points: [p] });
  };
  const move = (ev) => {
    if (!enTrace) return;
    const p = point(ev);
    const pts = enTrace.points;
    const last = pts[pts.length - 1];
    if (Math.hypot(p[0] - last[0], p[1] - last[1]) < 0.04) return;
    setEnTrace({ ...enTrace, points: enTrace.type === "cote" ? [pts[0], p] : [...pts, p] });
  };
  const up = () => {
    if (!enTrace) return;
    const t = enTrace;
    setEnTrace(null);
    if (t.type === "cote") {
      if (t.points.length < 2) return;
      const v = window.prompt(c.longueur);
      const m = parseFloat(String(v || "").replace(",", "."));
      if (m > 0) { memo(); setCotes((k) => [...k, { a: t.points[0], b: t.points[1], m }]); }
      return;
    }
    memo();
    setTraits((k) => [...k, t]);
  };
  const annuler = () => {
    const h = histo.current.pop();
    if (h) { setTraits(h.traits); setTextes(h.textes); setCotes(h.cotes); }
  };
  const effacer = () => {
    if (!traits.length && !textes.length && !cotes.length) return;
    if (!window.confirm(c.confirmer)) return;
    memo(); setTraits([]); setTextes([]); setCotes([]);
  };

  const grille = useMemo(() => {
    const out = [];
    const nx = Math.ceil(largeur / ppm), ny = Math.ceil(H / ppm);
    for (let i = 0; i <= nx; i += 1) out.push(<line key={`x${i}`} x1={i * ppm} y1={0} x2={i * ppm} y2={H} stroke={i % 5 ? "#eef2f0" : "#d9e2dd"} strokeWidth={1} />);
    for (let j = 0; j <= ny; j += 1) out.push(<line key={`y${j}`} x1={0} y1={j * ppm} x2={largeur} y2={j * ppm} stroke={j % 5 ? "#eef2f0" : "#d9e2dd"} strokeWidth={1} />);
    return out;
  }, [largeur, ppm]);

  const style = (type) => OUTILS.find((o) => o.id === type) || OUTILS[0];
  const chemin = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${(p[0] * ppm).toFixed(1)},${(p[1] * ppm).toFixed(1)}`).join(" ");
  const murs = traits.filter((t) => ["mur", "mur_ext", "cloison"].includes(t.type)).length;

  return (
    <div className="space-y-2" data-testid="atelier-croquis">
      <div className="flex flex-wrap items-center gap-1.5">
        {OUTILS.map((o) => (
          <Button key={o.id} size="sm" variant={outil === o.id ? "default" : "outline"} onClick={() => setOutil(o.id)} data-testid={`croquis-outil-${o.id}`}
            title={c[o.id]}>
            <o.icon className="h-4 w-4 sm:mr-1" style={o.couleur && outil !== o.id ? { color: o.couleur } : undefined} />
            <span className="hidden sm:inline">{c[o.id]}</span>
          </Button>
        ))}
        <span className="ml-auto flex gap-1.5">
          <Button size="sm" variant="ghost" onClick={() => setPpm((p) => Math.min(90, p + 8))} aria-label="zoom +"><ZoomIn className="h-4 w-4" /></Button>
          <Button size="sm" variant="ghost" onClick={() => setPpm((p) => Math.max(12, p - 8))} aria-label="zoom -"><ZoomOut className="h-4 w-4" /></Button>
          <Button size="sm" variant="outline" onClick={annuler} disabled={!histo.current.length} data-testid="croquis-annuler"><Undo2 className="h-4 w-4 mr-1" />{c.annuler}</Button>
          <Button size="sm" variant="outline" onClick={effacer}><Trash2 className="h-4 w-4 mr-1" />{c.effacer}</Button>
        </span>
      </div>
      <div ref={boite} className="rounded-xl border border-border bg-white overflow-hidden">
        <svg ref={svg} width={largeur} height={H} style={{ touchAction: "none", cursor: "crosshair", display: "block" }}
          onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={up} data-testid="croquis-feuille">
          {grille}
          {traits.map((t, i) => {
            const s = style(t.type);
            return <path key={i} d={chemin(t.points)} fill="none" stroke={s.couleur} strokeWidth={s.epaisseur} strokeLinecap="round" strokeLinejoin="round" />;
          })}
          {enTrace && enTrace.type !== "cote" && (
            <path d={chemin(enTrace.points)} fill="none" stroke={style(enTrace.type).couleur} strokeWidth={style(enTrace.type).epaisseur}
              strokeLinecap="round" strokeLinejoin="round" opacity={0.7} />
          )}
          {[...cotes, ...(enTrace?.type === "cote" && enTrace.points.length > 1 ? [{ a: enTrace.points[0], b: enTrace.points[1], m: null }] : [])].map((k, i) => (
            <g key={`c${i}`}>
              <line x1={k.a[0] * ppm} y1={k.a[1] * ppm} x2={k.b[0] * ppm} y2={k.b[1] * ppm} stroke="#c2410c" strokeWidth={1.5} strokeDasharray="6 4" />
              {k.m && (
                <text x={((k.a[0] + k.b[0]) / 2) * ppm} y={((k.a[1] + k.b[1]) / 2) * ppm - 6} fill="#c2410c" fontSize="13" textAnchor="middle" fontWeight="600">
                  {String(k.m).replace(".", ",")} m
                </text>
              )}
            </g>
          ))}
          {textes.map((t, i) => (
            <text key={`t${i}`} x={t.x * ppm} y={t.y * ppm} fill="#0f4c45" fontSize="14" textAnchor="middle" fontWeight="600">{t.nom}</text>
          ))}
        </svg>
      </div>
      <p className="text-xs text-muted-foreground">{c.aide}</p>
      <div className="flex justify-end">
        <Button onClick={() => (murs ? onRedresser({ traits, textes, cotes, y_bas: true }) : window.alert(c.vide))} disabled={enCours} data-testid="croquis-redresser">
          {enCours ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Wand2 className="h-4 w-4 mr-1" />}{c.redresser}
        </Button>
      </div>
    </div>
  );
}
