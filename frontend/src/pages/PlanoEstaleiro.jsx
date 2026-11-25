import { useEffect, useState } from "react";
import { Construction } from "lucide-react";
import { api } from "@/lib/api";
import PicTab from "@/components/tech/PicTab";

// Plano de estaleiro : app própria / app dédiée (plantas importadas = /takeoffs).
const dedupePlans = (items) => {
  const seen = new Set();
  return items.filter((p) => {
    const key = (p.filename || p.plan_id || "").trim().toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

export default function PlanoEstaleiro() {
  const [plans, setPlans] = useState([]);
  useEffect(() => {
    api.get("/takeoffs").then(({ data }) => {
      const items = Array.isArray(data) ? data : (data.items || data.takeoffs || data.plans || []);
      setPlans(dedupePlans(items));
    }).catch(() => {});
  }, []);
  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6" data-testid="pic-page">
      <div className="space-y-1">
        <div className="flex items-center gap-3 flex-wrap">
          <Construction className="h-6 w-6 text-primary" />
          <h1 className="font-display text-2xl font-bold">Plano de estaleiro</h1>
          <span className="text-[10px] font-bold uppercase bg-primary/10 text-primary px-2 py-0.5 rounded-full">Pro · Grua · Corte · 3D · Folha técnica</span>
        </div>
        <p className="text-sm text-muted-foreground max-w-3xl">A IA lê a planta de implantação, propõe a grua (modelo, lança, carga na ponta), as zonas de estaleiro, o corte vertical com as alturas e a vista 3D — validados por si.</p>
      </div>
      <PicTab plans={plans} />
    </div>
  );
}
