"""Lote 108 PT — Auditoria de site (heycatch, construpilot.pt) : correções da página inicial Pro.

Ganhos rápidos do plano de ação, na ordem da auditoria :
  D1.1/D2.1/D1.6  h1 com a categoria («Medições e orçamentos de obras, da planta ao acompanhamento»), ambição → faixa
  D1.2            linha de dor no hero + passos 01/02/03 reformulados em tarefas
  D1.3            8 cartões : frase da tarefa como título, nome do módulo como etiqueta
  D1.4            FAQ «Os meus dados são exportáveis?» / «O que acontece às minhas obras se cancelar?» + ligação privacidade
  D2.4 / brief    «sem débito antes do fim da experiência» + «Versão gratuita disponível para começar»
  D2.2            botão secundário «Ver a demonstração em vídeo» com destino #landing-demo
  D5.5            FAQPage em JSON-LD + descrições acessíveis das pré-visualizações e vídeos
  D3.1/D3.2       secção de prova real (contadores /api/reviews/site/usage, opiniões validadas, convite beta)
  D3.3/D3.5       página /sobre (equipa, contacto, LinkedIn), «Quem somos» no rodapé, sameAs, sitemap
Funciona com ou sem a «Auditoria V2 (2)» (abae6bd) aplicada. Idempotente. ARRÊT (nada escrito) se faltar uma âncora.
Uso : python3 lots/l108_auditoria_site/apply.py /app
"""
import pathlib
import re
import shutil
import sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/app")
here = pathlib.Path(__file__).resolve().parent
F = root / "frontend"
S = F / "src"
FILES = {
    "pro": S / "pages" / "LandingPro.jsx", "layout": S / "components" / "landing" / "LandingLayout.jsx",
    "trust": S / "components" / "TrustSection.jsx", "nav": S / "components" / "Nav.jsx", "app": S / "App.js",
    "seo": S / "seo" / "DefaultSEO.jsx", "css": S / "styles" / "landing-premium.css",
    "preview": S / "components" / "landing" / "ProductPreview.jsx", "demo": S / "components" / "DemoShowcase.jsx",
    "clips": S / "components" / "FeatureClips.jsx", "index": F / "public" / "index.html",
    "sitemap": F / "public" / "sitemap-pages.xml", "reviews": root / "backend" / "routes" / "reviews.py",
}
T = {k: p.read_text(encoding="utf-8") for k, p in FILES.items()}
if "LandingProof" in T["pro"]:
    print("já aplicado"); print("L108 OK"); sys.exit(0)


def stop(what):
    print("ÂNCORA não encontrada — ARRÊT, nada escrito:", what); sys.exit(1)


def rep(k, old, new, what, optional=False):
    if T[k].count(old) != 1:
        if optional:
            print("(opcional, ignorado)", what); return False
        stop(what)
    T[k] = T[k].replace(old, new, 1); return True


def rx(k, pat, repl, what, optional=False):
    if len(re.findall(pat, T[k])) != 1:
        if optional:
            print("(opcional, ignorado)", what); return False
        stop(what)
    T[k] = re.sub(pat, repl, T[k], count=1); return True


# ------------------------------------------------------------------ LandingPro
rep("pro", 'import { ProductPreview } from "@/components/landing/ProductPreview";',
    'import { ProductPreview } from "@/components/landing/ProductPreview";\nimport { LandingProof } from "@/components/landing/LandingProof";', "import ProductPreview")
FEATS = [
    ("metre", "Plantas e medições", "Meça a obra na planta, sem régua nem calculadora"),
    ("devis", "Orçamentos à sua imagem", "Responda ao cliente com um orçamento assinado antes de ele contratar outro"),
    ("factures", "Faturas e autos de medição", "Fature o que foi executado, auto a auto"),
    ("dpgf", "Mapa de quantidades e caderno de encargos", "Responda ao concurso depressa, com quantidades que pode defender"),
    ("escaliers", "Escadas 3D", "Mostre ao cliente a escada antes de a construir"),
    ("appro", "Aprovisionamento", "Tenha os materiais na obra no dia certo, sem custos surpresa"),
    ("multiniveaux", "Projetos multinível", "Some as quantidades de todos os pisos num só projeto"),
    ("equipe", "A sua equipa, reunida", "Passe de trabalhador independente a pequena empresa sem perder o fio"),
]
for fid, module, job in FEATS:
    rx("pro", r'(\{ id: "%s", icon: \w+, clip: [^,]+, )tag: "[^"]*", title: "%s",' % (fid, re.escape(module)),
       lambda m, module=module, job=job: f'{m.group(1)}tag: "{module}", title: "{job}",', f"cartão {fid}")
rep("pro", '  { q: "Pode ser utilizado no telemóvel?",', '''  { q: "Os meus dados são exportáveis?", a: "Sim. Os seus orçamentos e faturas descarregam-se em PDF e os mapas de quantidades e as medições em Excel, a qualquer momento. Pode também pedir a exportação completa dos seus dados (direito de portabilidade) para info@construpilot.pt." },
  { q: "O que acontece às minhas obras se cancelar?", a: "As suas obras e os seus documentos não são apagados quando cancela: deixa apenas de ter acesso às funções pagas e pode continuar a consultar e a descarregar os seus ficheiros. Se quiser que tudo seja apagado, elimina a conta e todos os dados na página construpilot.pt/eliminar-conta." },
  { q: "Pode ser utilizado no telemóvel?",''', "FAQ telemóvel")
# nota da experiência : versão dinâmica (abae6bd) ou texto fixo (antes)
if not rep("pro", '`Experiência de ${offer.trial_days} dias · cartão pedido · sem fidelização`',
           '`Experiência de ${offer.trial_days} dias · cartão pedido, sem débito antes do fim da experiência · sem fidelização`',
           "nota dinâmica", optional=True):
    rep("pro", "Experiência de 7 dias · Cartão obrigatório · Sem fidelização após a experiência",
        "Experiência de 7 dias · Cartão obrigatório, sem débito antes do fim da experiência · Sem fidelização após a experiência",
        "nota fixa da experiência")
rx("pro", r'(<p className="landing-hero-note">)(.*?)(</p>)',
   lambda m: m.group(1) + m.group(2) + ('{offerNote ? " · " : ""}' if m.group(2).strip() == "{offerNote}" else " · ")
   + '<Link to="/confidentialite" data-testid="pro-hero-privacy">Os seus dados e a privacidade</Link>' + m.group(3),
   "nota do hero")
rx("pro", r'jsonLd=\{\{"@context":"https://schema.org","@type":"SoftwareApplication",(.*?)\}\} />',
   lambda m: 'jsonLd={{"@context":"https://schema.org","@graph":[{"@type":"SoftwareApplication",' + m.group(1)
   + '},{"@type":"FAQPage",mainEntity:FAQ.map(f=>({"@type":"Question",name:f.q,acceptedAnswer:{"@type":"Answer",text:f.a}}))}]}} />',
   "jsonLd SoftwareApplication")
rep("pro", '<h1>O futuro não se espera, constrói-se<br /><em>Ambição, liderança e inovação</em></h1>',
    '<h1>Medições e orçamentos de obras,<br /><em>da planta ao acompanhamento</em></h1>\n'
    '        <p className="landing-hero-pain" data-testid="pro-hero-pain">Chega de medir à mão e repetir orçamentos em folhas de cálculo.</p>', "h1")
rx("pro", r'<button type="button" className="landing-button landing-button-outline" onClick=\{showDemo\} data-testid="pro-hero-secondary-cta">(<Play size=\{16\} />)Ver a demonstração</button>',
   lambda m: '<a href="#landing-demo" className="landing-button landing-button-outline" onClick={e=>{e.preventDefault();showDemo();}} data-testid="pro-hero-secondary-cta">' + m.group(1) + 'Ver a demonstração em vídeo</a>',
   "botão demonstração")
rep("pro", '<strong>Mais espaço para a sua profissão.</strong>', '<strong>O futuro não se espera, constrói-se.</strong>', "faixa", optional=True)
rep("pro", '{title:"Reúna",desc:"As plantas, as peças do processo e os pedidos do cliente.",icon:Ruler},{title:"Prepare",desc:"Quantidades controladas e um orçamento construído artigo a artigo.",icon:FileText},{title:"Faça a gestão",desc:"Os documentos, as próximas ações e as conversas da equipa.",icon:Users}',
    '{title:"Responda ao concurso depressa",desc:"As plantas, as peças do processo e o pedido do cliente no mesmo sítio, para orçamentar no próprio dia.",icon:Ruler},{title:"Confie nas quantidades",desc:"Medições controladas na planta e um orçamento construído artigo a artigo, sem refazer as contas à mão.",icon:FileText},{title:"Responda ao cliente primeiro",desc:"Os documentos, as próximas ações e as conversas da equipa à mão, para não perder a obra por responder tarde.",icon:Users}',
    "passos 01/02/03")
rx("pro", r'(\n( *)<LandingPricing plans=\{PLANS\} pro />\n)', lambda m: m.group(1) + m.group(2) + "<LandingProof />\n", "LandingPricing")

# ------------------------------------------------------------------ ofertas : versão gratuita visível
rep("layout", 'import "@/styles/landing-premium.css";', 'import "@/styles/landing-premium.css";\nimport { PricingFreeLine } from "@/components/landing/LandingProof";', "import css layout")
rx("layout", r'(<LandingHeading eyebrow="Ao seu ritmo"[^\n]*</LandingHeading>\n)', lambda m: m.group(1) + '    {pro && <PricingFreeLine />}\n', "título ofertas")

# ------------------------------------------------------------------ prova, página Sobre, rodapé, SEO
rep("trust", "\nconst ReviewDialog = (", "\nexport const ReviewDialog = (", "ReviewDialog", optional=True)
if "export const ReviewDialog" not in T["trust"]:
    stop("ReviewDialog exportável")
rx("app", r'(import Investors from "@/pages/Investors";\n)', lambda m: m.group(1) + 'import About from "@/pages/About";\n', "import Investors")
rx("app", r'(\n( *)<Route path="/investisseurs"[^\n]*\n)',
   lambda m: m.group(1) + m.group(2) + '<Route path="/sobre" element={<About />} />\n' + m.group(2) + '<Route path="/about" element={<Navigate to="/sobre" replace />} />\n',
   "rota /investisseurs")
if not re.search(r'import \{[^}]*\bNavigate\b[^}]*\} from "react-router-dom"', T["app"]):
    stop("Navigate importado em App.js")
rx("nav", r'(\n( *)Ajuda e assistência\n( *)</Link>\n)',
   lambda m: m.group(1) + f'{m.group(3)}<Link\n{m.group(3)}  to="/sobre"\n{m.group(3)}  className="text-[11px] text-muted-foreground/70 hover:text-primary transition-colors"\n'
   f'{m.group(3)}  data-testid="footer-about-link"\n{m.group(3)}>\n{m.group(2)}Quem somos\n{m.group(3)}</Link>\n', "rodapé Ajuda", optional=True)
rep("index", '"sameAs": []', '"sameAs": ["https://www.linkedin.com/in/construpilot-construpilot-00189942a"]', "sameAs", optional=True)
rx("seo", r'(\n  "/investisseurs":)', lambda m: '\n  "/sobre": { title: "Sobre o ConstruPilot: a equipa por trás do produto", description: "Quem construiu o ConstruPilot, como contactar os fundadores e onde nos encontrar." },' + m.group(1),
   "SEO /investisseurs", optional=True)
if "construpilot.pt/sobre" not in T["sitemap"] and T["sitemap"].rstrip().endswith("</urlset>"):
    T["sitemap"] = T["sitemap"].rstrip()[:-len("</urlset>")] + ('  <url>\n    <loc>https://construpilot.pt/sobre</loc>\n    <changefreq>monthly</changefreq>\n'
                    '    <priority>0.6</priority>\n    <xhtml:link rel="alternate" hreflang="pt-PT" href="https://construpilot.pt/sobre" />\n  </url>\n\n</urlset>\n')
rep("preview", 'aria-label="Ilustração de uma planta com divisões e medidas a controlar"',
    'aria-label="Planta de uma habitação no ConstruPilot com sala, quarto, cozinha e casa de banho, cotada para medir áreas e comprimentos"', "svg planta", optional=True)
rep("preview", '<div className="landing-demo-document">', '<div className="landing-demo-document" role="img" aria-label="Editor de orçamento ConstruPilot com capítulos de obra e total sem IVA">', "orçamento demo", optional=True)
rep("preview", '<div className="landing-demo-tasks">', '<div className="landing-demo-tasks" role="img" aria-label="Processo de obra no ConstruPilot com plantas, orçamento e próxima visita">', "tarefas demo", optional=True)
rep("demo", '            data-testid="demo-video"', '            data-testid="demo-video"\n            aria-label="Demonstração em vídeo do ConstruPilot: da planta ao orçamento"', "vídeo demo", optional=True)
rep("clips", '                data-testid={`feature-clip-video-${f.key}`}', '                data-testid={`feature-clip-video-${f.key}`}\n                aria-label={`Vídeo da função ${f.title || f.key} no ConstruPilot`}', "vídeos funções", optional=True)

# ------------------------------------------------------------------ backend : contadores reais
rep("reviews", '@router.get("/site/pending", dependencies=[Depends(admin_user)])', '''@router.get("/site/usage")
async def site_usage() -> dict:
    """Auditoria de site (D3.1) : contadores públicos reais da beta (nunca valores fixos no código).

    Conta as contas não-admin e os projetos de obra; a página só mostra o contador acima de um mínimo."""
    users = await db.users.count_documents({"role": {"$ne": "admin"}})
    projects = await db.projects.count_documents({})
    return {"beta_users": int(users), "projects": int(projects)}


@router.get("/site/pending", dependencies=[Depends(admin_user)])''', "rota /reviews/site/pending")
compile(T["reviews"], "reviews.py", "exec")
CSS = (here / "landing-audit.css").read_text(encoding="utf-8")
if "landing-proof-counters" not in T["css"]:
    T["css"] = T["css"].rstrip("\n") + "\n\n" + CSS

# ------------------------------------------------------------------ escrita
for k, p in FILES.items():
    p.write_text(T[k], encoding="utf-8")
shutil.copy(here / "LandingProof.jsx", S / "components" / "landing" / "LandingProof.jsx")
shutil.copy(here / "About.jsx", S / "pages" / "About.jsx")
print("L108 OK")
