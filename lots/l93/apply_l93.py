"""Lot 93 (FR + PT) — fiabilité de l'estimateur « construction maison » (test de bout en bout du 06/11).

Constats (test réel construpilot.pt, moradia T3 140 m² em Leiria, du pedido au orçamento final) :
 1. Landing /particuliers → /estimation : la description saisie était perdue (le formulaire restait sur
    « rénovation complète · Lisbonne · 100 m² »). Maintenant l'IA pré-remplit le formulaire automatiquement.
 2. Prix éco / premium « €/m² » faux pour les particuliers : la majoration +30 % ne touchait pas `per_sqm`
    (821 €/m² affiché au lieu de 1 068 €/m²). `per_sqm` ajouté aux clés monétaires.
 3. Évacuation des déchets comptée deux fois (poste « Déchets / évacuation » + frais forfaitaires du même nom).
    Les frais forfaitaires ne s'appliquent plus si le poste existe déjà ; la tuile n'est affichée que si > 0.
 4. Économies : l'optimisation fournisseurs (6 %) était recalculée sur les matériaux déjà optimisés (-8 %) —
    double comptage ; mention interne « Tavily » retirée ; badge « ROI ×2 159 » absurde masqué au-delà de ×100.
 5. Toast « Valores por defeito aplicados : finish_level, building_type » : clés techniques → libellés.
 6. PT uniquement : libellés « Outro » (main d'œuvre / location matériel), « Toiture », outils « IVA »
    (= VAT, détecteur de tension) et « Piso » (= niveau), placeholder e-mail « vous@exemple.fr », « soit », « lot(s) ».
Usage : python3 lots/l93/apply_l93.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre obligatoire manque ;
« optionnel, ignoré » acceptable pour les ancres de texte)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
MARK = "CP-FIAB-EST"
TAG = "L93"

# (fichier, ancien, nouveau, obligatoire)
COMMON = [
    ("backend/engines/estimation.py",
     "    waste = round(surface * 9 * rc, 2)\n",
     "    # CP-FIAB-EST : si le poste « déchets / évacuation » est déjà chiffré, pas de frais forfaitaires en double.\n"
     "    waste = 0.0 if any(l.get(\"key\") == \"dechets\" for l in lots) else round(surface * 9 * rc, 2)\n", True),
    ("backend/engines/estimation.py",
     '"price_per_sqm", "min", "max"', '"price_per_sqm", "per_sqm", "min", "max"', True),
    ("backend/engines/savings.py",
     '''    materials = est.get("breakdown", {}).get("materials", 0)
    pct = 0.06
    amount = round(materials * pct, 2)''',
     '''    materials = est.get("breakdown", {}).get("materials", 0)
    pct = 0.06
    # CP-FIAB-EST : appliqué aux matériaux déjà optimisés (-8 %), sinon la même économie est comptée deux fois.
    amount = round(materials * (1 - 0.08) * pct, 2)''', True),
    ("frontend/src/components/SavingsCard.jsx",
     "{data.roi_multiplier > 5 && (", "{data.roi_multiplier > 5 && data.roi_multiplier <= 100 && (", False),
]

PT = [
    ("backend/engines/savings.py", "via comparador Tavily", "após otimização, via comparador de fornecedores", False),
    ("backend/engines/savings.py", "{len(switched)} lot(s) :", "{len(switched)} lote(s):", False),
    ("backend/engines/savings.py", "em {len(switched)} lot(s)'", "em {len(switched)} lote(s)'", False),
    ("backend/engines/savings.py", "f', soit {roi_multiplier}×", "f', ou seja {roi_multiplier}×", False),
    ("backend/engines/catalog.py", '"key": "toiture", "name": "Toiture"', '"key": "toiture", "name": "Cobertura"', False),
    ("backend/engines/catalog.py", '"Martelo perfurador", "IVA"]', '"Martelo perfurador", "Detetor de tensão"]', False),
    ("backend/engines/catalog.py", '"Piso", ', '"Nível de bolha", ', False),
    ("backend/engines/catalog.py", ', "Piso"]', ', "Nível de bolha"]', False),
    ("backend/engines/diy.py", '["Piso", "Cruzetas"]', '["Nível de bolha", "Cruzetas"]', False),
    ("backend/engines/diy.py", '"tools": ["IVA"]', '"tools": ["Detetor de tensão"]', False),
    ("frontend/src/components/EstimationView.jsx",
     '<Stat label="Outro" value={eur(b.labour)}', '<Stat label="Mão de obra" value={eur(b.labour)}', False),
    ("frontend/src/components/EstimationView.jsx",
     '<Stat label="Outro" value={eur(b.equipment_rental)}', '<Stat label="Aluguer de equipamento" value={eur(b.equipment_rental)}', False),
    ("frontend/src/components/EstimationView.jsx",
     '<TableHead className="text-right">Outro</TableHead>', '<TableHead className="text-right">Mão de obra</TableHead>', False),
    ("frontend/src/components/EstimationView.jsx",
     '        <Stat label="Resíduos / evacuação" value={eur(b.waste_disposal)} testId="stat-waste" />',
     '        {b.waste_disposal > 0 && <Stat label="Resíduos / evacuação" value={eur(b.waste_disposal)} testId="stat-waste" />}', True),
    ("frontend/src/pages/LandingParticuliers.jsx", 'placeholder="vous@exemple.fr"', 'placeholder="voce@exemplo.pt"', False),
    ("frontend/src/pages/Estimator.jsx", "const CONDITION_LABEL = {",
     '''// CP-FIAB-EST : libellés lisibles des champs remplis par défaut (jamais les clés techniques).
const FIELD_LABEL = {
  finish_level: "nível de acabamento (Standard)", building_type: "tipo de edifício (Moradia)",
  condition: "estado atual (Bom estado)", region: "região", city: "cidade", surface: "área",
  construction_year: "ano de construção", project_type: "tipo de obras",
};

const CONDITION_LABEL = {''', True),
    ("frontend/src/pages/Estimator.jsx",
     'toast.message("Valores por defeito aplicados", { description: data.defaults_used.join(", ") });',
     'toast.message("Valores por defeito aplicados", { description: data.defaults_used.map((k) => FIELD_LABEL[k] || k).join(", ") });', True),
    ("frontend/src/pages/Estimator.jsx", '  const [name, setName] = useState("");\n',
     '  const [name, setName] = useState("");\n  const [pendingPrompt, setPendingPrompt] = useState("");\n', True),
    ("frontend/src/pages/Estimator.jsx",
     '''        description: a.summary || a._raw || a.description || f.description,
      }));
      toast.success(t("est.imported"));
    } catch { /* ignore */ }
  }, []);
''',
     '''        description: a.summary || a._raw || a.description || f.description,
      }));
      // CP-FIAB-EST : vindo da landing só com texto livre → a IA pré-preenche tipo de obra, área, região…
      if (!a.project_type && (a._raw || a.description)) setPendingPrompt(a._raw || a.description);
      toast.success(t("est.imported"));
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!pendingPrompt || !catalog || !user) return;
    const prompt = pendingPrompt;
    setPendingPrompt("");
    api.post("/prompt-fill/estimativa", { prompt, contexto: {} })
      .then(({ data }) => {
        if (data?.params && Object.keys(data.params).length) applyPromptFill(data);
        if (data?.clarification_question) toast.info(data.clarification_question, { duration: 8000 });
      })
      .catch(() => { /* a barra «Gerar» continua disponível */ });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPrompt, catalog, user]);
''', True),
]

FR = [
    ("backend/engines/savings.py", "via comparateur Tavily", "après optimisation, via comparateur fournisseurs", False),
    ("frontend/src/components/EstimationView.jsx",
     '        <Stat label="Déchets / évacuation" value={eur(b.waste_disposal)} testId="stat-waste" />',
     '        {b.waste_disposal > 0 && <Stat label="Déchets / évacuation" value={eur(b.waste_disposal)} testId="stat-waste" />}', True),
    ("frontend/src/pages/Estimator.jsx", "const CONDITION_LABEL = {",
     '''// CP-FIAB-EST : libellés lisibles des champs remplis par défaut (jamais les clés techniques).
const FIELD_LABEL = {
  finish_level: "niveau de finition (Standard)", building_type: "type de bâtiment (Maison)",
  condition: "état actuel (Bon état)", region: "région", city: "ville", surface: "surface",
  construction_year: "année de construction", project_type: "type de travaux",
};

const CONDITION_LABEL = {''', True),
    ("frontend/src/pages/Estimator.jsx",
     'toast.message("Valeurs par défaut appliquées", { description: data.defaults_used.join(", ") });',
     'toast.message("Valeurs par défaut appliquées", { description: data.defaults_used.map((k) => FIELD_LABEL[k] || k).join(", ") });', True),
    ("frontend/src/pages/Estimator.jsx", '  const [catalog, setCatalog] = useState(null);\n',
     '  const [catalog, setCatalog] = useState(null);\n  const [pendingPrompt, setPendingPrompt] = useState("");\n', True),
    ("frontend/src/pages/Estimator.jsx",
     '''        description: a.summary || a._raw || a.description || f.description,
      }));
      toast.success(t("est.imported"));
    } catch { /* ignore */ }
  }, []);
''',
     '''        description: a.summary || a._raw || a.description || f.description,
      }));
      // CP-FIAB-EST : venu de la landing avec un texte libre → l'IA pré-remplit type, surface, région…
      if (!a.project_type && (a._raw || a.description)) setPendingPrompt(a._raw || a.description);
      toast.success(t("est.imported"));
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!pendingPrompt || !catalog) return;
    const prompt = pendingPrompt;
    setPendingPrompt("");
    aiFill(prompt);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPrompt, catalog]);
''', True),
]

# Contrôle avant écriture : toutes les ancres obligatoires présentes (ou déjà remplacées), sinon ARRÊT.
plan = COMMON + (PT if site == "pt" else FR)
files = {}
for rel, old, new, req in plan:
    p = root / rel
    if rel not in files:
        if not p.exists():
            print(f"ARRÊT : fichier absent {rel} — rien écrit"); sys.exit(1)
        files[rel] = p.read_text(encoding="utf-8")
    s = files[rel]
    if new in s:
        continue
    if old not in s:
        if req:
            print(f"ARRÊT : ancre absente dans {rel} : {old[:70]!r} — rien écrit"); sys.exit(1)
        print(f"optionnel, ignoré : {rel} : {old[:50]!r}")
        continue
    files[rel] = s.replace(old, new)
for rel, s in files.items():
    (root / rel).write_text(s, encoding="utf-8")
import shutil  # noqa: E402
t_src = pathlib.Path(__file__).resolve().parent / "tests" / f"test_l{TAG[1:]}.py"
if t_src.exists():
    shutil.copy(t_src, root / "backend" / "tests" / t_src.name)
print(f"{TAG} {site.upper()} OK")
