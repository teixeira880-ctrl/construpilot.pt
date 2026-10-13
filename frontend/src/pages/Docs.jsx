import { useState } from "react";
import { Link } from "react-router-dom";
import { Copy, Check, ArrowRight, Zap, Package, Search, Calculator, Code2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "sonner";
import { SectionTitle } from "@/components/Bits";

const CURL_EST = `curl -X POST https://pilot-build-demo.preview.emergentagent.com/api/v1/public/estimation \\ -H "X-API-Key: ckp_live_..." \\ -H "Content-Type: application/json" \\ -d '{ "project_type": "renovation_complete", "surface": 80, "finish_level": "standard", "country": "PT", "region": "Lisboa", "building_type": "apartamento", "condition": "bom" }'`;

const CURL_PRICES = `curl -X POST https://pilot-build-demo.preview.emergentagent.com/api/v1/public/prices \\
  -H "X-API-Key: ckp_live_..." \\
  -H "Content-Type: application/json" \\
  -d '{"query":"carrelage 60x60","limit":10}'`;

const CURL_CALC = `curl -X POST https://pilot-build-demo.preview.emergentagent.com/api/v1/public/calculators \\
  -H "X-API-Key: ckp_live_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "kind":"paint",
    "params":{"length":5,"width":4,"height":2.5,"doors":1,"windows":2,"coats":2}
  }'`;

const JS_SNIPPET = `import axios from "axios"; const api = axios.create({ baseURL: "https://pilot-build-demo.preview.emergentagent.com/api/v1/public", headers: { "X-API-Key": process.env.CONSTRUPILOT_KEY }, }); const { data } = await api.post("/estimation", { project_type: "renovation_partielle", surface: 45, finish_level: "standard", }); console.log(data.data.total_avg);`;

const USE_CASES = [
  { icon: Package, title: "Distribuidor de materiais",
    desc: "Adicione um simulador de renovação ao seu site comercial. Converta os visitantes em carrinhos médios superiores graças à estimativa antes da compra." },
  { icon: Zap, title: "Constructeur / Franchise",
    desc: "Estime instantaneamente o orçamento de um cliente na sua sala de exposição, gere um PDF marcado com o seu logótipo e converta no local." },
  { icon: Search, title: "Agência imobiliária",
    desc: "Orçamente as renovações de um imóvel durante a visita. Venda melhor mostrando o custo real dos trabalhos." },
  { icon: Calculator, title: "Assureur",
    desc: "Estime os sinistros e renovações pós-incidente através do nosso motor. Reduza os prazos de perícia." },
];

const CodeBlock = ({ code, testid }) => {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1500); toast.success("Copiado"); }
    catch { toast.error("Cópia impossível"); }
  };
  return (
    <div className="relative group">
      <pre className="text-xs bg-secondary/40 border border-border p-4 rounded-sm overflow-x-auto" data-testid={testid}>
        <code>{code}</code>
      </pre>
      <button onClick={copy} className="absolute top-2 right-2 h-8 w-8 grid place-items-center rounded-sm bg-background/80 hover:bg-primary hover:text-primary-foreground transition-colors opacity-0 group-hover:opacity-100" aria-label="Copier">
        {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      </button>
    </div>
  );
};

export default function Docs() {
  return (
    <div className="grid gap-12">
      <SectionTitle as="h1" over="ConstruPilot Developers" title="Integre o nosso motor de estimativa com a API">
        Uma API REST simples, documentada, pronta para produção. Prototipagem em Starter (99 €/mês), volumes elevados em Business (299 €) ou Scale (999 €). Sandbox ilimitada durante a integração.
      </SectionTitle>

      <div className="grid md:grid-cols-4 gap-4" data-testid="docs-usecases">
        {USE_CASES.map((u, i) => (
          <div key={i} className="surface p-5 grid gap-3">
            <span className="h-10 w-10 grid place-items-center rounded-sm bg-primary/15 text-primary">
              <u.icon className="h-5 w-5" />
            </span>
            <p className="font-display font-bold">{u.title}</p>
            <p className="text-xs text-muted-foreground leading-relaxed">{u.desc}</p>
          </div>
        ))}
      </div>

      <div className="surface p-8 grid gap-6">
        <div className="flex items-center gap-3">
          <Code2 className="h-5 w-5 text-primary" />
          <p className="overline">Iniciar</p>
        </div>
        <ol className="grid gap-4 text-sm">
          <li className="flex gap-3">
            <span className="num h-7 w-7 rounded-full bg-primary/15 text-primary grid place-items-center text-xs font-bold shrink-0">1</span>
            <span>Subscreva o plano <Link to="/tarifs" className="text-primary underline">API Starter, Business ou Scale</Link> desde a página Tarifas.</span>
          </li>
          <li className="flex gap-3">
            <span className="num h-7 w-7 rounded-full bg-primary/15 text-primary grid place-items-center text-xs font-bold shrink-0">2</span>
            <span>Gere a sua primeira chave a partir de<Link to="/developpeurs" className="text-primary underline">Espaço Programadores</Link>. Elle commence par <code className="bg-secondary px-1 rounded-sm">ckp_live_</code>.</span>
          </li>
          <li className="flex gap-3">
            <span className="num h-7 w-7 rounded-full bg-primary/15 text-primary grid place-items-center text-xs font-bold shrink-0">3</span>
            <span>Envie o seu primeiro pedido (exemplos abaixo). Passe a chave no cabeçalho <code className="bg-secondary px-1 rounded-sm">X-API-Key</code>.</span>
          </li>
        </ol>
      </div>

      <Tabs defaultValue="estimation" data-testid="docs-tabs">
        <TabsList className="rounded-sm">
          <TabsTrigger value="estimation" className="rounded-sm" data-testid="docs-tab-estimation">Estimation</TabsTrigger>
          <TabsTrigger value="prices" className="rounded-sm" data-testid="docs-tab-prices">Preços de materiais</TabsTrigger>
          <TabsTrigger value="calculators" className="rounded-sm" data-testid="docs-tab-calculators">Calculateurs</TabsTrigger>
          <TabsTrigger value="js" className="rounded-sm" data-testid="docs-tab-js">Node.js / axios</TabsTrigger>
        </TabsList>

        <TabsContent value="estimation" className="mt-6 grid gap-4">
          <h3 className="font-display font-bold text-lg">POST /api/v1/public/estimation</h3>
          <p className="text-sm text-muted-foreground">Devolve o custo total, a repartição por lote, o planeamento e os indicadores de risco.</p>
          <CodeBlock code={CURL_EST} testid="docs-code-estimation" />
        </TabsContent>
        <TabsContent value="prices" className="mt-6 grid gap-4">
          <h3 className="font-display font-bold text-lg">POST /api/v1/public/prices</h3>
          <p className="text-sm text-muted-foreground">Preço materiais em tempo real nas 10 principais insígnias francesas via Tavily.</p>
          <CodeBlock code={CURL_PRICES} testid="docs-code-prices" />
        </TabsContent>
        <TabsContent value="calculators" className="mt-6 grid gap-4">
          <h3 className="font-display font-bold text-lg">POST /api/v1/public/calculators</h3>
          <p className="text-sm text-muted-foreground">
            Types : <code className="bg-secondary px-1 rounded-sm">paint</code>,{" "}
            <code className="bg-secondary px-1 rounded-sm">tile</code>,{" "}
            <code className="bg-secondary px-1 rounded-sm">drywall</code>,{" "}
            <code className="bg-secondary px-1 rounded-sm">concrete</code>,{" "}
            <code className="bg-secondary px-1 rounded-sm">insulation</code>.
          </p>
          <CodeBlock code={CURL_CALC} testid="docs-code-calc" />
        </TabsContent>
        <TabsContent value="js" className="mt-6 grid gap-4">
          <h3 className="font-display font-bold text-lg">Cliente Node.js</h3>
          <CodeBlock code={JS_SNIPPET} testid="docs-code-js" />
        </TabsContent>
      </Tabs>

      <div className="surface p-8 grid md:grid-cols-2 gap-6 items-center">
        <div>
          <p className="font-display text-2xl font-extrabold tracking-tighter">Pronto para integrar?</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Comece com <b>API Starter a 99 €/mês</b> — 1 000 chamadas incluídas, upgrade instantâneo.
          </p>
        </div>
        <div className="flex flex-wrap gap-3 justify-end">
          <Link to="/tarifs"><Button data-testid="docs-cta-pricing" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">Ver as tarifas API <ArrowRight className="h-4 w-4" /></Button></Link>
          <Link to="/enterprise"><Button variant="outline" className="rounded-sm">Falar com um especialista</Button></Link>
        </div>
      </div>
    </div>
  );
}
