import { useEffect, useMemo, useState } from "react";
import { Home, BedDouble, Layers, Ruler, Car, Waves, Trees, Sun, Briefcase, Shirt, Sparkles, Loader2, Minus, Plus, Shapes } from "lucide-react";
import { Button } from "@/components/ui/button";
import { programaSimples, areaMinima } from "./programaSimples";

// Modo simples do Ateliê: escolhas com botões, sem nada para escrever. O assistente escreve ele próprio um programa
// detalhado (divisões com área, por piso) que o motor lê à letra — o resultado é a mesma maqueta editável no Estúdio.
// Áreas tipo confortáveis (acima dos mínimos do RGEU / logement décent), ajustadas à área total escolhida.

const TXT = {
  pt: {
    titulo: "Diga-nos como imagina a sua casa", quartos: "Quartos", pisos: "Pisos", um: "Térreo", dois: "2 pisos", area: "Área aproximada", minimo: "mín. realista",
    garagem: "Garagem", sem: "Sem", carro1: "1 carro", carro2: "2 carros", cobertura: "Telhado", plana: "Plano (moderno)", duas: "2 águas", quatro: "4 águas",
    estilo: "Estilo", moderno: "Moderno", contemporaneo: "Contemporâneo", tradicional: "Tradicional", extras: "Extras",
    provencal: "Provençal", rustico: "Rústico", mediterranico: "Mediterrânico", escandinavo: "Escandinavo", forma: "Forma", retangular: "Retangular", formaL: "Em L (com recortes)",
    suite: "Suite com closet", escritorio: "Escritório", lavandaria: "Lavandaria", piscina: "Piscina", jardim: "Jardim", terraco: "Terraço com pérgola",
    criar: "Criar a minha casa", ver: "Ver o texto gerado", nota: "Tudo continua editável depois no Estúdio: paredes, divisões, janelas, materiais, piscina…",
  },
  fr: {
    titulo: "Dites-nous comment vous imaginez votre maison", quartos: "Chambres", pisos: "Niveaux", um: "Plain-pied", dois: "R+1", area: "Surface approximative", minimo: "min. réaliste",
    garagem: "Garage", sem: "Sans", carro1: "1 voiture", carro2: "2 voitures", cobertura: "Toiture", plana: "Toit plat (moderne)", duas: "2 pans", quatro: "4 pans",
    estilo: "Style", moderno: "Moderne", contemporaneo: "Contemporain", tradicional: "Traditionnel", extras: "Options",
    provencal: "Provençal", rustico: "Rustique", mediterranico: "Méditerranéen", escandinavo: "Scandinave", forma: "Forme", retangular: "Rectangulaire", formaL: "En L (décrochements)",
    suite: "Suite parentale avec dressing", escritorio: "Bureau", lavandaria: "Buanderie", piscina: "Piscine", jardim: "Jardin", terraco: "Terrasse avec pergola",
    criar: "Créer ma maison", ver: "Voir le texte généré", nota: "Tout reste modifiable ensuite dans le Studio : murs, pièces, fenêtres, matériaux, piscine…",
  },
  en: {
    titulo: "Tell us how you imagine your house", quartos: "Bedrooms", pisos: "Storeys", um: "Single storey", dois: "2 storeys", area: "Approximate area", minimo: "realistic min.",
    garagem: "Garage", sem: "None", carro1: "1 car", carro2: "2 cars", cobertura: "Roof", plana: "Flat (modern)", duas: "Gable", quatro: "Hip",
    estilo: "Style", moderno: "Modern", contemporaneo: "Contemporary", tradicional: "Traditional", extras: "Extras",
    provencal: "Provençal", rustico: "Rustic", mediterranico: "Mediterranean", escandinavo: "Scandinavian", forma: "Shape", retangular: "Rectangular", formaL: "L-shaped",
    suite: "Master suite with walk-in closet", escritorio: "Office", lavandaria: "Laundry", piscina: "Pool", jardim: "Garden", terraco: "Terrace with pergola",
    criar: "Create my house", ver: "See the generated text", nota: "Everything stays editable in the Studio: walls, rooms, windows, materials, pool…",
  },
};

function Grupo({ icon: Icon, rotulo, children }) {
  return <div className="space-y-1.5">
    <p className="text-xs font-medium text-muted-foreground flex items-center gap-1"><Icon className="h-3.5 w-3.5" />{rotulo}</p>
    <div className="flex flex-wrap gap-1.5">{children}</div>
  </div>;
}

function Chip({ ativo, onClick, children, testid }) {
  return <button type="button" onClick={onClick} data-testid={testid}
    className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${ativo ? "bg-primary text-primary-foreground border-primary" : "bg-card border-border hover:border-primary/60"}`}>
    {children}
  </button>;
}

export default function AssistenteSimples({ lang = "pt", onGerar, ocupado }) {
  const t = TXT[lang] || TXT.pt;
  const [o, setO] = useState({ quartos: 3, pisos: 2, area: 180, garagem: 2, cobertura: "plana", estilo: "moderno", forma: "R",
    suite: true, escritorio: true, lavandaria: true, piscina: false, jardim: true, terraco: false });
  const [ver, setVer] = useState(false);
  const p = (k, v) => setO((x) => ({ ...x, [k]: v }));
  const minimo = areaMinima(o);
  useEffect(() => { if (o.area < minimo) setO((x) => ({ ...x, area: minimo })); }, [minimo, o.area]);
  const texto = useMemo(() => programaSimples(o, lang), [o, lang]);
  const alt = (k) => p(k, !o[k]);
  return (
    <div className="space-y-4" data-testid="atelier-simples">
      <p className="font-medium flex items-center gap-1.5"><Home className="h-4 w-4 text-primary" />{t.titulo}</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Grupo icon={BedDouble} rotulo={t.quartos}>
          <Button size="icon" variant="outline" className="h-8 w-8" onClick={() => p("quartos", Math.max(1, o.quartos - 1))} aria-label="−"><Minus className="h-4 w-4" /></Button>
          <span className="min-w-8 text-center text-lg font-semibold" data-testid="atelier-simples-quartos">{o.quartos}</span>
          <Button size="icon" variant="outline" className="h-8 w-8" onClick={() => p("quartos", Math.min(6, o.quartos + 1))} aria-label="+"><Plus className="h-4 w-4" /></Button>
        </Grupo>
        <Grupo icon={Layers} rotulo={t.pisos}>
          <Chip ativo={o.pisos === 1} onClick={() => p("pisos", 1)}>{t.um}</Chip>
          <Chip ativo={o.pisos === 2} onClick={() => p("pisos", 2)}>{t.dois}</Chip>
        </Grupo>
        <Grupo icon={Ruler} rotulo={`${t.area}: ${o.area} m² (${t.minimo} ${minimo} m²)`}>
          <input type="range" min={minimo} max={Math.max(400, minimo + 100)} step={10} value={o.area} onChange={(e) => p("area", Number(e.target.value))}
            className="w-full accent-[hsl(var(--primary))]" data-testid="atelier-simples-area" />
        </Grupo>
        <Grupo icon={Car} rotulo={t.garagem}>
          {[[0, t.sem], [1, t.carro1], [2, t.carro2]].map(([v, l]) => <Chip key={v} ativo={o.garagem === v} onClick={() => p("garagem", v)}>{l}</Chip>)}
        </Grupo>
        <Grupo icon={Sun} rotulo={t.cobertura}>
          {[["plana", t.plana], ["duas", t.duas], ["quatro", t.quatro]].map(([v, l]) => <Chip key={v} ativo={o.cobertura === v} onClick={() => p("cobertura", v)}>{l}</Chip>)}
        </Grupo>
        <Grupo icon={Sparkles} rotulo={t.estilo}>
          {[["moderno", t.moderno], ["contemporaneo", t.contemporaneo], ["tradicional", t.tradicional], ["provencal", t.provencal], ["rustico", t.rustico],
            ["mediterranico", t.mediterranico], ["escandinavo", t.escandinavo]].map(([v, l]) => <Chip key={v} ativo={o.estilo === v} onClick={() => p("estilo", v)}>{l}</Chip>)}
        </Grupo>
        <Grupo icon={Shapes} rotulo={t.forma}>
          <Chip ativo={o.forma === "R"} onClick={() => p("forma", "R")}>{t.retangular}</Chip>
          <Chip ativo={o.forma === "L"} onClick={() => p("forma", "L")} testid="atelier-simples-forma-l">{t.formaL}</Chip>
        </Grupo>
      </div>
      <Grupo icon={Plus} rotulo={t.extras}>
        <Chip ativo={o.suite} onClick={() => alt("suite")}><Shirt className="inline h-3.5 w-3.5 mr-1" />{t.suite}</Chip>
        <Chip ativo={o.escritorio} onClick={() => alt("escritorio")}><Briefcase className="inline h-3.5 w-3.5 mr-1" />{t.escritorio}</Chip>
        <Chip ativo={o.lavandaria} onClick={() => alt("lavandaria")}>{t.lavandaria}</Chip>
        <Chip ativo={o.piscina} onClick={() => alt("piscina")} testid="atelier-simples-piscina"><Waves className="inline h-3.5 w-3.5 mr-1" />{t.piscina}</Chip>
        <Chip ativo={o.jardim} onClick={() => alt("jardim")}><Trees className="inline h-3.5 w-3.5 mr-1" />{t.jardim}</Chip>
        <Chip ativo={o.terraco} onClick={() => alt("terraco")}>{t.terraco}</Chip>
      </Grupo>
      <p className="text-xs text-muted-foreground">{t.nota}</p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button type="button" className="text-xs text-primary hover:underline" onClick={() => setVer(!ver)}>{t.ver}</button>
        <Button size="lg" disabled={ocupado} onClick={() => onGerar(texto, o.area)} data-testid="atelier-simples-criar">
          {ocupado ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Home className="h-4 w-4 mr-1" />}{t.criar}
        </Button>
      </div>
      {ver && <pre className="text-xs whitespace-pre-wrap rounded-lg bg-secondary/50 p-3 max-h-64 overflow-auto">{texto}</pre>}
    </div>
  );
}
