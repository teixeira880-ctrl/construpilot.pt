/**
 * Blog em português (Portugal) — servido em /blog quando o idioma é PT.
 * Artigos pensados para o mercado português (custos, IVA/CIVA, método).
 */

export const BLOG_ARTICLES_PT = [
  {
    slug: "custo-renovacao-portugal-2026",
    title: "Quanto custa renovar em Portugal em 2026: preços €/m² por distrito",
    excerpt:
      "Remodelação de apartamento ou moradia? Veja as faixas de preço €/m² por distrito em 2026 (Lisboa, Porto, Algarve…), os lotes a prever e como estimar a sua obra em minutos.",
    published: "2026-06-25",
    updated: "2026-06-25",
    cover: "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=1200&q=80",
    category: "Renovação",
    readingMinutes: 6,
    keywords:
      "custo renovação Portugal, preço remodelação m2, preço obras Lisboa, preço remodelação Porto, orçamento renovação casa, quanto custa renovar apartamento",
  },
  {
    slug: "iva-obras-portugal-6-23",
    title: "IVA nas obras em Portugal: 23% ou 6% na reabilitação (Verba 2.27 do CIVA)",
    excerpt:
      "Quando se aplica a taxa reduzida de 6% de IVA nas empreitadas de reabilitação de habitação e quando é 23%? Guia prático 2026 para particulares e profissionais.",
    published: "2026-06-25",
    updated: "2026-06-25",
    cover: "https://images.unsplash.com/photo-1554224155-6726b3ff858f?w=1200&q=80",
    category: "Fiscalidade",
    readingMinutes: 5,
    keywords:
      "IVA obras Portugal, IVA 6 reabilitação, Verba 2.27 CIVA, taxa reduzida IVA construção, IVA remodelação habitação, IVA 23 construção",
  },
  {
    slug: "estimar-obra-5-minutos",
    title: "Como estimar uma obra em 5 minutos com o ConstruPilot",
    excerpt:
      "Sem horas em Excel. Descreva o projeto, deixe a IA calcular os lotes, materiais e mão de obra, e obtenha um orçamento com IVA e NIF pronto a enviar ao cliente.",
    published: "2026-06-25",
    updated: "2026-06-25",
    cover: "https://images.unsplash.com/photo-1541888946425-d81bb19240f5?w=1200&q=80",
    category: "Método",
    readingMinutes: 5,
    keywords:
      "estimar obra Portugal, orçamento obras rápido, software orçamentos construção, estimativa custo obra IA, orçamento com IVA e NIF",
  },
  {
    slug: "licenciamento-obras-portugal",
    title: "Licenciamento de obras em Portugal: quando precisa de licença ou só comunicação prévia",
    excerpt:
      "Obras isentas, comunicação prévia ou licença camarária? Guia 2026 para saber que autorização precisa antes de começar a sua remodelação ou construção.",
    published: "2026-06-26",
    updated: "2026-06-26",
    cover: "https://images.unsplash.com/photo-1503387762-592deb58ef4e?w=1200&q=80",
    category: "Licenciamento",
    readingMinutes: 6,
    keywords:
      "licenciamento obras Portugal, comunicação prévia obras, licença camarária, obras isentas licença, RJUE, autorização de utilização",
  },
  {
    slug: "orcamento-casa-de-banho-portugal",
    title: "Quanto custa remodelar uma casa de banho em Portugal em 2026",
    excerpt:
      "Preços por m², lotes de trabalho e onde poupar numa remodelação de casa de banho. Estime a sua em minutos, com IVA a 6% quando elegível.",
    published: "2026-06-26",
    updated: "2026-06-26",
    cover: "https://images.unsplash.com/photo-1620626011761-996317b8d101?w=1200&q=80",
    category: "Renovação",
    readingMinutes: 5,
    keywords:
      "orçamento casa de banho, preço remodelação casa de banho, custo wc m2, remodelar casa de banho Portugal, preço azulejos e loiças",
  },
  {
    slug: "eficiencia-energetica-certificado-portugal",
    title: "Eficiência energética e certificado energético: o que muda nas obras em 2026",
    excerpt:
      "Certificado energético, isolamento, janelas e bombas de calor: como melhorar a classe energética da sua casa e valorizar o imóvel.",
    published: "2026-06-26",
    updated: "2026-06-26",
    cover: "https://images.unsplash.com/photo-1509395176047-4a66953fd231?w=1200&q=80",
    category: "Eficiência",
    readingMinutes: 6,
    keywords:
      "certificado energético Portugal, eficiência energética casa, classe energética, isolamento térmico, bomba de calor, reabilitação energética",
  },
];

export const getArticlePT = (slug) => BLOG_ARTICLES_PT.find((a) => a.slug === slug);

const H2 = ({ children }) => (
  <h2 className="font-display text-xl font-bold mt-8 mb-2 text-foreground">{children}</h2>
);

export const ARTICLE_BODIES_PT = {
  "custo-renovacao-portugal-2026": (
    <>
      <p>
        O custo de uma renovação em Portugal em 2026 depende sobretudo do distrito, do estado do
        imóvel e do nível de acabamento. Em reabilitação, as faixas de mercado situam-se
        tipicamente entre <strong>500 e 1 100 €/m²</strong>, podendo ultrapassar esse valor em
        acabamentos de gama alta ou em zonas de forte procura.
      </p>
      <H2>Faixas indicativas por distrito (reabilitação, €/m², sem IVA)</H2>
      <ul className="list-disc pl-5 space-y-1">
        <li><strong>Lisboa:</strong> 750 – 1 400 €/m²</li>
        <li><strong>Porto:</strong> 650 – 1 250 €/m²</li>
        <li><strong>Algarve (Faro):</strong> 700 – 1 300 €/m²</li>
        <li><strong>Setúbal:</strong> 600 – 1 150 €/m²</li>
        <li><strong>Braga / Aveiro / Coimbra:</strong> 500 – 980 €/m²</li>
        <li><strong>Madeira / Açores:</strong> 650 – 1 200 €/m²</li>
      </ul>
      <H2>Principais lotes de uma remodelação</H2>
      <p>
        Demolições, canalização, eletricidade, revestimentos (azulejos e pavimentos), pinturas,
        carpintarias, cozinha e casas de banho. As casas de banho e a cozinha são, quase sempre, os
        lotes mais caros por m².
      </p>
      <H2>Estime a sua obra em segundos</H2>
      <p>
        Em vez de trabalhar com médias, descreva o seu projeto no ConstruPilot e obtenha uma
        estimativa detalhada por lote, ajustada ao seu distrito — com a taxa de IVA correta (6% na
        reabilitação elegível, 23% nos restantes casos).
      </p>
    </>
  ),
  "iva-obras-portugal-6-23": (
    <>
      <p>
        Em Portugal, os serviços de construção estão, por regra, sujeitos à taxa normal de IVA de
        <strong> 23%</strong>. No entanto, as empreitadas de <strong>reabilitação de imóveis de
        habitação</strong> podem beneficiar da <strong>taxa reduzida de 6%</strong>, ao abrigo da
        <strong> Verba 2.27 da Lista I anexa ao CIVA</strong>.
      </p>
      <H2>Quando se aplica a taxa de 6%?</H2>
      <p>
        A taxa reduzida aplica-se, em termos gerais, às empreitadas de beneficiação, remodelação,
        renovação, restauro, reparação ou conservação de imóveis (ou partes) afetos à
        <strong> habitação</strong>, com exceção dos materiais que representem parte significativa
        do valor quando faturados isoladamente. Confirme sempre o enquadramento com o seu
        contabilista.
      </p>
      <H2>Quando é 23%?</H2>
      <p>
        Construção nova, imóveis não habitacionais (comércio, escritórios), e fornecimento isolado
        de materiais tendem a ficar sujeitos à taxa normal de 23%.
      </p>
      <H2>Faturação correta no ConstruPilot</H2>
      <p>
        No ConstruPilot pode escolher a taxa por linha (6% / 13% / 23%). Ao gerar um orçamento a
        partir de uma descrição de reabilitação de habitação, a taxa de <strong>6%</strong> é
        aplicada automaticamente — e as suas faturas incluem o NIF e, se quiser, o Alvará.
      </p>
    </>
  ),
  "estimar-obra-5-minutos": (
    <>
      <p>
        Estimar uma obra costuma consumir horas em folhas de cálculo. Com o ConstruPilot, o processo
        demora cerca de <strong>5 minutos</strong> e resulta num orçamento pronto a enviar.
      </p>
      <H2>1. Descreva o projeto</H2>
      <p>
        Escreva em linguagem simples («remodelar a cozinha de uma moradia: canalização, azulejos,
        pintura») ou importe uma planta. A IA identifica os lotes de trabalho.
      </p>
      <H2>2. Deixe a IA calcular</H2>
      <p>
        Materiais, mão de obra e quantidades são estimados a partir da sua biblioteca de preços e do
        distrito. O IVA aplicável (6% ou 23%) é sugerido automaticamente.
      </p>
      <H2>3. Ajuste e envie</H2>
      <p>
        Reveja as linhas, aplique a sua margem e envie o orçamento por e-mail — com o seu NIF, IVA
        correto e, opcionalmente, um render 3D antes/depois. O cliente pode assinar online.
      </p>
      <p className="mt-4">
        <strong>Resultado:</strong> menos tempo administrativo, orçamentos mais profissionais e
        clientes com mais confiança.
      </p>
    </>
  ),
  "licenciamento-obras-portugal": (
    <>
      <p>
        Antes de começar uma obra em Portugal, é essencial saber que autorização é necessária. O
        Regime Jurídico da Urbanização e Edificação (<strong>RJUE</strong>) prevê três situações
        principais: obras isentas de controlo prévio, comunicação prévia e licença camarária.
      </p>
      <H2>Obras isentas de licença</H2>
      <p>
        Pequenas intervenções de conservação e reparação que não alterem a estrutura, a fachada nem
        a volumetria (ex.: pintar, substituir revestimentos, trocar loiças) estão geralmente isentas.
        Confirme sempre com a câmara municipal, pois há especificidades locais e em zonas
        classificadas.
      </p>
      <H2>Comunicação prévia</H2>
      <p>
        Aplica-se, em regra, a obras de reconstrução, alteração ou ampliação dentro de determinados
        limites e em zonas com plano em vigor. É submetida no portal da câmara e permite iniciar a
        obra após o prazo legal, salvo indeferimento.
      </p>
      <H2>Licença de obras (controlo prévio)</H2>
      <p>
        Necessária para construção nova, ampliações relevantes ou alterações de uso. Exige projeto de
        arquitetura e especialidades, aprovado pela câmara, e termina com a <strong>autorização de
        utilização</strong>.
      </p>
      <H2>E o orçamento?</H2>
      <p>
        Independentemente da autorização, estime primeiro o custo. Com o ConstruPilot obtém uma
        estimativa por lote em minutos e um orçamento com IVA (6% na reabilitação elegível) e NIF.
      </p>
      <p className="text-xs text-muted-foreground mt-4">
        Este artigo é informativo e não dispensa a consulta da câmara municipal ou de um técnico.
      </p>
    </>
  ),
  "orcamento-casa-de-banho-portugal": (
    <>
      <p>
        A casa de banho é, por m², um dos espaços mais caros de remodelar. Em Portugal, em 2026, uma
        remodelação completa situa-se tipicamente entre <strong>3 000 € e 9 000 €</strong>, consoante
        a área, a qualidade dos materiais e o distrito.
      </p>
      <H2>Principais lotes</H2>
      <ul className="list-disc pl-5 space-y-1">
        <li>Demolição e remoção de entulho</li>
        <li>Canalização e esgotos (redes de água quente/fria)</li>
        <li>Eletricidade e iluminação</li>
        <li>Impermeabilização e assentamento de azulejos/pavimento</li>
        <li>Loiças sanitárias, torneiras e móvel</li>
        <li>Pintura e acabamentos</li>
      </ul>
      <H2>Onde poupar (sem perder qualidade)</H2>
      <p>
        Mantenha a localização das redes (mudar tudo de sítio encarece), escolha azulejo de formato
        standard e concentre o orçamento nas peças que usa todos os dias (torneiras, base de duche).
      </p>
      <H2>IVA a 6%</H2>
      <p>
        Numa habitação elegível, a remodelação da casa de banho pode beneficiar da taxa reduzida de
        <strong> 6%</strong> (Verba 2.27 do CIVA). No ConstruPilot, essa taxa é aplicada
        automaticamente ao orçamento.
      </p>
    </>
  ),
  "eficiencia-energetica-certificado-portugal": (
    <>
      <p>
        Melhorar a eficiência energética reduz as faturas e valoriza o imóvel. O <strong>certificado
        energético</strong> (obrigatório para vender ou arrendar) classifica a casa de A+ a F e
        indica medidas de melhoria.
      </p>
      <H2>Medidas com maior impacto</H2>
      <ul className="list-disc pl-5 space-y-1">
        <li><strong>Isolamento térmico</strong> da envolvente (paredes, cobertura) — o maior ganho</li>
        <li><strong>Janelas eficientes</strong> com vidro duplo e corte térmico</li>
        <li><strong>Bomba de calor</strong> para AQS e climatização</li>
        <li>Painéis <strong>solares/fotovoltaicos</strong></li>
        <li>Iluminação LED e ventilação controlada</li>
      </ul>
      <H2>Subir de classe energética</H2>
      <p>
        Combinar isolamento + janelas + bomba de calor pode fazer subir várias classes, com retorno
        no conforto e na fatura. Há programas de apoio à reabilitação energética que convém consultar.
      </p>
      <H2>Estime o custo das medidas</H2>
      <p>
        Descreva as intervenções no ConstruPilot (isolamento, janelas, AVAC) e obtenha uma estimativa
        por lote, com IVA a 6% quando se trata de reabilitação de habitação elegível.
      </p>
    </>
  ),
};
