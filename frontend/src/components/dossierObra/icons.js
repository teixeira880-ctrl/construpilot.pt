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
