import { Building2, Cog, HardHat, CalendarRange, ShieldCheck, Layers, BrickWall, Diamond, Triangle, Grid2X2, Network, Droplet, Zap, Fan, AudioLines, Radio,
  Flame, Sun, Home, Trees, PaintRoller, DoorOpen, Hammer, Wrench, Accessibility, Mountain, Waves, CloudRain, ThermometerSun, Cpu, Package, FileText,
  ClipboardCheck, Recycle, Truck, Users, Ruler, Camera, MessageSquare, Euro, Repeat, BookOpen, Building, Square } from "lucide-react";

export const AREA_ICONS = { arquitetura: Building2, engenharia: Cog, preparacao: HardHat, gestao: CalendarRange, entrega: ShieldCheck };
export const AREA_SHORT = { arquitetura: "Arquitetura", engenharia: "Engenharia", preparacao: "Preparação e segurança", gestao: "Gestão e execução", entrega: "Entrega e manutenção" };

export const SPEC_ICONS = {
  implantacao: Layers, paredes: BrickWall, revest_exteriores: Diamond, revest_interiores: Diamond, pavimentos: Square, coberturas: Triangle, tetos: Square,
  caixilharias: Grid2X2, carpintarias: Hammer, serralharias: Wrench, pinturas: PaintRoller, acessibilidade: Accessibility, arranjos_exteriores: Trees,
  levantamentos: Mountain, estruturas: Network, contencoes: Building, agua: Droplet, residuais: Droplet, pluviais: CloudRain, eletricidade: Zap,
  ited: Radio, climatizacao: Fan, aqs: ThermometerSun, gas: Flame, termica: AudioLines, acustica: AudioLines, incendio: ShieldCheck, solar: Sun,
  domotica: Cpu, especiais: Cog, administrativo: FileText, terreno: Mountain, estaleiro: HardHat, demolicoes: Hammer, seguranca: ShieldCheck,
  residuos: Recycle, provisorios: Wrench, planeamento: CalendarRange, equipas: Users, compras: Truck, custos: Euro, autos: Ruler, alteracoes: Repeat,
  diario: Camera, qualidade: ClipboardCheck, comunicacoes: MessageSquare, inspecoes: ClipboardCheck, rececao: Home, telas_finais: FileText,
  manuais: BookOpen, manutencao: Wrench, dossier_final: Package,
};
export const specIcon = (key) => SPEC_ICONS[key] || Layers;

// Cores modernas por módulo (gradiente suave, glifo branco). O cobre fica reservado ao módulo selecionado.
const G = {
  verde: ["#3fcf8e", "#1f8a5b"], azul: ["#7dd3fc", "#0369a1"], indigo: ["#a5b4fc", "#4f46e5"], violeta: ["#d8b4fe", "#7e22ce"],
  rosa: ["#f9a8d4", "#be185d"], vermelho: ["#fca5a5", "#c0262d"], laranja: ["#fdba74", "#c2410c"], ambar: ["#fcd34d", "#b45309"],
  lima: ["#bef264", "#4d7c0f"], teal: ["#5eead4", "#0f766e"], ciano: ["#67e8f9", "#0e7490"], ardosia: ["#cbd5e1", "#475569"],
};
export const AREA_COLORS = { arquitetura: G.verde, engenharia: G.azul, preparacao: G.ambar, gestao: G.indigo, entrega: G.rosa };
export const SPEC_COLORS = {
  implantacao: G.verde, paredes: G.laranja, revest_exteriores: G.teal, revest_interiores: G.ciano, pavimentos: G.ambar, coberturas: G.vermelho,
  tetos: G.ardosia, caixilharias: G.azul, carpintarias: G.laranja, serralharias: G.ardosia, pinturas: G.rosa, acessibilidade: G.indigo, arranjos_exteriores: G.lima,
  levantamentos: G.lima, estruturas: G.ardosia, contencoes: G.ambar, agua: G.azul, residuais: G.teal, pluviais: G.ciano, eletricidade: G.ambar,
  ited: G.violeta, climatizacao: G.ciano, aqs: G.vermelho, gas: G.laranja, termica: G.rosa, acustica: G.indigo, incendio: G.vermelho, solar: G.ambar,
  domotica: G.violeta, especiais: G.ardosia, administrativo: G.indigo, terreno: G.lima, estaleiro: G.ambar, demolicoes: G.vermelho, seguranca: G.verde,
  residuos: G.lima, provisorios: G.ardosia, planeamento: G.indigo, equipas: G.violeta, compras: G.teal, custos: G.verde, autos: G.azul, alteracoes: G.laranja,
  diario: G.rosa, qualidade: G.verde, comunicacoes: G.ciano, inspecoes: G.ambar, rececao: G.verde, telas_finais: G.azul, manuais: G.violeta,
  manutencao: G.teal, dossier_final: G.laranja,
};
export const COPPER = ["#e5a26b", "#9a5530"];
const grad = ([a, b]) => `linear-gradient(135deg, ${a}, ${b})`;

/** Logótipo do módulo: quadrado arredondado em gradiente com glifo branco. */
export function ModuleIcon({ k, area, size = 18, tile = 30, radius, copper = false, className = "" }) {
  const Icon = k ? specIcon(k) : (AREA_ICONS[area] || Layers);
  const colors = copper ? COPPER : (k ? (SPEC_COLORS[k] || AREA_COLORS[area] || G.verde) : (AREA_COLORS[area] || G.verde));
  return (
    <span className={`cp-module-icon ${className}`} aria-hidden="true"
      style={{ width: tile, height: tile, borderRadius: radius ?? Math.round(tile * 0.3), background: grad(colors) }}>
      <Icon size={size} strokeWidth={2.1} color="#fff" />
    </span>
  );
}
