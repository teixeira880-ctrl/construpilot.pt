import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

// Perfil de trabalho (apresentação apenas). Permissões e plano continuam a ser validados no servidor.
export const MODES = [
  { key: "guiado", label: "Guiado", hint: "Uma pergunta de cada vez, com exemplos" },
  { key: "direto", label: "Direto", hint: "Formulários compactos e atalhos" },
  { key: "avancado", label: "Avançado", hint: "Todos os parâmetros técnicos" },
];

export function useWorkProfile() {
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    api.get("/me/work-profile").then(({ data }) => alive && setProfile(data)).catch(() => alive && setError(true));
    return () => { alive = false; };
  }, []);
  const save = useCallback(async (patch) => {
    const { data } = await api.put("/me/work-profile", patch);
    setProfile(data);
    window.dispatchEvent(new CustomEvent("cp:work-profile", { detail: data }));
    return data;
  }, []);
  useEffect(() => {
    const on = (e) => setProfile(e.detail);
    window.addEventListener("cp:work-profile", on);
    return () => window.removeEventListener("cp:work-profile", on);
  }, []);
  // Sem perfil (erro de rede, conta antiga): modo guiado e linguagem simples, nada bloqueado.
  const effective = profile || { mode: "guiado", language: "simples", professions: [], onboarding: "pending" };
  return { profile: effective, loaded: !!profile || error, save };
}

// Glossário: linguagem simples ↔ técnica. Simplificar nunca retira a informação necessária.
const GLOSSARY = {
  unit_price: { simples: "Preço por unidade, sem IVA", tecnica: "P.U. s/ IVA" },
  qty: { simples: "Quantidade", tecnica: "Qtd." },
  procurement: { simples: "Materiais e encomendas", tecnica: "Aprovisionamento" },
  scale: { simples: "Indique uma medida real da planta", tecnica: "Calibrar a escala" },
  yield: { simples: "Quantos m² pinta 1 litro (numa demão)", tecnica: "Rendimento (m²/L/demão)" },
  coats: { simples: "Quantas camadas de tinta", tecnica: "N.º de demãos" },
  waste: { simples: "Margem para cortes e quebras (%)", tecnica: "Perdas (%)" },
  openings: { simples: "Portas e janelas (não se pintam)", tecnica: "Vãos a deduzir" },
  ceiling_height: { simples: "Altura do chão ao teto", tecnica: "Pé-direito" },
};
export const term = (key, language = "simples") => GLOSSARY[key]?.[language] || GLOSSARY[key]?.simples || key;

export const fmt = (v, d = 2) => v == null ? "—" : Number(v).toLocaleString("pt-PT", { maximumFractionDigits: d });

// Gera um identificador de pedido estável (evita duplicados em reenvio).
export const newRequestId = () => (crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`).replace(/-/g, "").slice(0, 32);
