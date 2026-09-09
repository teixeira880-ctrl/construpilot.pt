import { motion } from "framer-motion";
import { Boxes, Layers, MapPin, PlugZap, CheckCircle2 } from "lucide-react";
import { useI18n } from "@/context/I18nContext";

const FEATURES_FR = [
  { icon: Layers, title: "Déboursé sec automatique",
    desc: "Coût de revient et prix de vente calculés par ouvrage : matériaux + main d'œuvre + pertes, marge appliquée." },
  { icon: MapPin, title: "Coefficients régionaux",
    desc: "Prix ajustés automatiquement selon la zone : Île-de-France, grandes villes ou rural." },
  { icon: PlugZap, title: "Connexion fournisseurs",
    desc: "Prêt à connecter Point.P, Chausson, Gedimat, Leroy Merlin… pour actualiser les prix matériaux." },
];
const FEATURES_PT = [
  { icon: Layers, title: "Custo direto automático",
    desc: "Custo de produção e preço de venda calculados por trabalho: materiais + mão de obra + perdas, com margem aplicada." },
  { icon: MapPin, title: "Coeficientes por distrito",
    desc: "Preços ajustados automaticamente à zona: Lisboa, Porto, Algarve, interior…" },
  { icon: PlugZap, title: "Ligação a fornecedores",
    desc: "Pronto para ligar a fornecedores de materiais e atualizar os preços." },
];

/** Section pub : bibliothèque paramétrique ConstruPilot (ouvrages composés). */
export function ParamLibraryPromo() {
  const { lang } = useI18n();
  const pt = lang === "pt";
  const FEATURES = pt ? FEATURES_PT : FEATURES_FR;
  return (
    <section className="relative overflow-hidden border-y border-border bg-[#0A0D14] text-white"
             data-testid="param-promo">
      <div className="absolute inset-0 opacity-[0.07]"
           style={{ backgroundImage: "radial-gradient(circle at 20% 30%, #3F7D54 0, transparent 45%), radial-gradient(circle at 80% 70%, #C9A227 0, transparent 45%)" }} />
      <div className="relative mx-auto max-w-[1500px] px-6 lg:px-10 py-24 lg:py-28">
        <div className="grid lg:grid-cols-[1.1fr,1fr] gap-14 items-center">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/40 bg-primary/10 px-4 py-1.5 text-xs font-semibold text-primary uppercase tracking-wider">
              <Boxes className="h-4 w-4" /> {pt ? "Novo · Motor de orçamentação" : "Nouveau · Moteur de chiffrage"}
            </div>
            <h2 className="mt-6 text-4xl sm:text-5xl font-black leading-[1.05] tracking-tight">
              {pt
                ? <>Uma biblioteca de <span className="text-primary">218&nbsp;trabalhos compostos</span>, orçamentados ao real.</>
                : <>Une bibliothèque de <span className="text-primary">218&nbsp;ouvrages composés</span>, chiffrés au réel.</>}
            </h2>
            <p className="mt-6 text-lg text-white/70 max-w-xl leading-relaxed">
              {pt
                ? "Acabaram os preços «a olho». Cada trabalho é decomposto em materiais, mão de obra e perdas, com fórmulas de quantidade paramétricas. O ConstruPilot calcula o custo direto, o custo de produção e o preço de venda — ajustado ao seu distrito e à sua margem."
                : "Fini les prix « au doigt mouillé ». Chaque ouvrage est décomposé en matériaux, main d'œuvre et pertes, avec des formules de quantité paramétriques. ConstruPilot calcule pour vous le déboursé sec, le coût de revient et le prix de vente — ajusté à votre région et votre marge."}
            </p>
            <div className="mt-8 flex flex-wrap gap-x-8 gap-y-3">
              {(pt
                ? ["1 127 linhas de receitas", "13 especialidades", "Custos horários 2026", "IVA 6 / 13 / 23 %"]
                : ["1 127 lignes de recettes", "13 corps de métier", "Taux horaires 2026", "TVA 5,5 / 10 / 20 %"]
              ).map((t) => (
                <div key={t} className="flex items-center gap-2 text-sm text-white/80">
                  <CheckCircle2 className="h-4 w-4 text-primary" /> {t}
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-4">
            {FEATURES.map((f, i) => (
              <motion.div key={f.title} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }}
                          viewport={{ once: true }} transition={{ delay: i * 0.1 }}
                          className="rounded-xl border border-white/10 bg-white/[0.04] backdrop-blur-sm p-5 flex gap-4">
                <div className="shrink-0 h-11 w-11 rounded-lg bg-primary/15 flex items-center justify-center">
                  <f.icon className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <p className="font-semibold">{f.title}</p>
                  <p className="text-sm text-white/60 mt-1 leading-relaxed">{f.desc}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export default ParamLibraryPromo;
