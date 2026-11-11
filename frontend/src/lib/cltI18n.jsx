// CLT page (/clt-industrial) in Portuguese, English and Ukrainian.
//
// The page is written in Portuguese. LangScope translates the visible texts, placeholders, titles and options of
// its subtree: first with UI below, then with the dossier dictionary served by the backend
// (GET /clt-industrial/i18n/:lang: parameter labels, library items, stages, sources), then with PATTERNS for
// texts with numbers. Texts with no translation stay in Portuguese, so nothing disappears.
import { useEffect, useRef } from "react";

export const CLT_LANGS = { pt: "PT", en: "EN", uk: "УКР" };

// Portuguese → [English, Ukrainian]
const UI = {
  // navigation and access
  "ConstruPilot CLT": ["ConstruPilot CLT", "ConstruPilot CLT"],
  "Piloto CLT": ["CLT pilot", "Пілот CLT"],
  "Desenhos e medições": ["Drawings and take-off", "Креслення та обміри"],
  "Juntas, corte, 3D e fabrico": ["Joints, cutting, 3D and fabrication", "Вузли, розкрій, 3D і виробництво"],
  "Custos, preços e plano": ["Costs, prices and plan", "Витрати, ціни та план"],
  "Seguimento e avanço": ["Tracking and progress", "Контроль і прогрес"],
  "Tarifas dos lotes": ["Package rates", "Тарифи пакетів"],
  "A verificar o acesso…": ["Checking access…", "Перевірка доступу…"],
  "O piloto CLT está indisponível nesta conta.": ["The CLT pilot is not available for this account.", "Пілот CLT недоступний для цього облікового запису."],
  "Língua da página": ["Page language", "Мова сторінки"],
  // drawings
  "PDF vetorial": ["Vector PDF", "Векторний PDF"],
  "Desenho CAD": ["CAD drawing", "Креслення CAD"],
  "Ler referências": ["Read references", "Зчитати позначення"],
  "Medir contornos": ["Measure outlines", "Обміряти контури"],
  "Medir painéis de um DWG ou DXF": ["Measure panels from a DWG or DXF", "Обміряти панелі з DWG або DXF"],
  "A processar o desenho…": ["Processing the drawing…", "Обробка креслення…"],
  "A carregar a folha…": ["Loading the sheet…", "Завантаження аркуша…"],
  "Folha": ["Sheet", "Аркуш"],
  "Selecionar": ["Select", "Вибрати"],
  "Localizar troço ou cota de escala": ["Locate a run or the scale dimension", "Знайти ділянку або масштабний розмір"],
  "Selecione uma referência para localizar a origem no desenho. As anotações precisam de revisão antes de servir de base ao fabrico.": [
    "Select a reference to locate its origin on the drawing. The annotations must be reviewed before they are used for fabrication.",
    "Виберіть позначення, щоб знайти його на кресленні. Анотації потрібно перевірити, перш ніж використовувати їх для виробництва."],
  "Sem cotas ou anotações reconhecidas automaticamente nesta folha.": ["No dimensions or notes recognised automatically on this sheet.", "На цьому аркуші автоматично не розпізнано розмірів чи анотацій."],
  "Confirme a unidade no desenho.": ["Confirm the unit on the drawing.", "Перевірте одиницю на кресленні."],
  "Verde: medido em planta": ["Green: measured on plan", "Зелений: обміряно на плані"],
  "Azul: área declarada": ["Blue: declared area", "Синій: заявлена площа"],
  "Âmbar: associação por confirmar": ["Amber: link to be confirmed", "Бурштиновий: зв'язок потрібно підтвердити"],
  "CLT em planta": ["CLT on plan", "CLT на плані"],
  "Base interior declarada": ["Declared interior base", "Заявлена внутрішня площа"],
  "Área de revestimento": ["Lining area", "Площа облицювання"],
  "Volume CLT": ["CLT volume", "Об'єм CLT"],
  "Volume de revestimento": ["Lining volume", "Об'єм облицювання"],
  "Paredes, lintéis, laje, coberturas, vigas, vãos e divisões por piso, cada elemento com a folha e a referência de origem.": [
    "Walls, lintels, slab, roofs, beams, openings and rooms per floor, each element with its source sheet and reference.",
    "Стіни, перемички, перекриття, покрівлі, балки, отвори та приміщення по поверхах, кожен елемент з аркушем і позначенням джерела."],
  "Medições por piso": ["Take-off per floor", "Обміри по поверхах"],
  "Divisão": ["Room", "Приміщення"], "Tipo": ["Type", "Тип"], "Área": ["Area", "Площа"], "Aparelhos": ["Fixtures", "Прилади"],
  "Lados a confirmar": ["Sides to confirm", "Сторони для перевірки"],
  "Elemento CLT": ["CLT element", "Елемент CLT"], "Espessura confirmada (mm)": ["Confirmed thickness (mm)", "Підтверджена товщина (мм)"],
  "Comprimento medido (m)": ["Measured length (m)", "Обміряна довжина (м)"], "Área indicada": ["Stated area", "Вказана площа"],
  "Vão indicado": ["Stated opening", "Вказаний отвір"], "Material indicado": ["Stated material", "Вказаний матеріал"],
  "Por confirmar": ["To be confirmed", "Потрібно підтвердити"], "Lintéis": ["Lintels", "Перемички"],
  "Camada dos painéis": ["Panel layer", "Шар панелей"], "Camada dos recortes": ["Cut-out layer", "Шар вирізів"],
  "Área líquida": ["Net area", "Площа нетто"], "Volume bruto": ["Gross volume", "Об'єм брутто"], "Volume líquido": ["Net volume", "Об'єм нетто"],
  "Descarregar modelo 3D (IFC)": ["Download 3D model (IFC)", "Завантажити 3D-модель (IFC)"],
  "Calculado por": ["Calculated by", "Розраховано"],
  "Pré-visualizar": ["Preview", "Попередній перегляд"],
  // engines tab
  "Leitura automática das paredes CLT num PDF vetorial, juntas sem contagem dupla, plano de corte nos painéis de prensa (formato da sua prensa, por omissão 18 × 3,5 m), modelo 3D IFC verificado e desenhos de fabrico. Tudo o que é lido fica \"detetado, por confirmar\" até conferência.": [
    "Automatic reading of the CLT walls on a vector PDF, joints without double counting, cutting plan on the press panels (your press format, 18 × 3.5 m by default), checked IFC 3D model and fabrication drawings. Everything read stays \"detected, to be confirmed\" until checked.",
    "Автоматичне зчитування стін CLT з векторного PDF, вузли без подвійного підрахунку, план розкрою на пресових панелях (формат вашого преса, за замовчуванням 18 × 3,5 м), перевірена 3D-модель IFC і виробничі креслення. Усе зчитане має статус «виявлено, потрібно підтвердити» до перевірки."],
  "Painel de prensa (m)": ["Press panel (m)", "Пресова панель (м)"],
  "Comprimento do painel de prensa (m)": ["Press panel length (m)", "Довжина пресової панелі (м)"],
  "Largura do painel de prensa (m)": ["Press panel width (m)", "Ширина пресової панелі (м)"],
  "empresa": ["company", "компанія"],
  "Rezult, características técnicas (clt-rezult.com/en/technical-characteristics), lido em 2026-11-11": [
    "Rezult technical characteristics (clt-rezult.com/en/technical-characteristics), read 2026-11-11",
    "Технічні характеристики Rezult (clt-rezult.com/en/technical-characteristics), переглянуто 2026-11-11"],
  "Planta em PDF vetorial": ["Plan as vector PDF", "План у векторному PDF"],
  "Piso": ["Floor", "Поверх"],
  "Cota da base das paredes (m)": ["Wall base level (m)", "Відмітка низу стін (м)"],
  "Página": ["Page", "Сторінка"],
  "Altura estrutural das paredes (m)": ["Structural wall height (m)", "Конструктивна висота стін (м)"],
  "Escala 1: (vazio = ler na folha)": ["Scale 1: (empty = read on the sheet)", "Масштаб 1: (порожньо = зчитати з аркуша)"],
  "Camadas": ["Layers", "Шари"],
  "Cor dos lintéis (ex. #ff0000)": ["Lintel colour (e.g. #ff0000)", "Колір перемичок (напр. #ff0000)"],
  "vazio = só se houver uma cor": ["empty = only if there is one colour", "порожньо = лише якщо колір один"],
  "Ler paredes do PDF": ["Read walls from the PDF", "Зчитати стіни з PDF"],
  "A ler…": ["Reading…", "Зчитування…"],
  "Paredes": ["Walls", "Стіни"], "Comprimento (m)": ["Length (m)", "Довжина (м)"], "Volume bruto (m³)": ["Gross volume (m³)", "Об'єм брутто (м³)"],
  "Juntas": ["Joints", "Вузли"], "Escala": ["Scale", "Масштаб"], "Retirar": ["Remove", "Прибрати"],
  "altura standard": ["standard height", "стандартна висота"], "standard 3,00": ["standard 3.00", "стандарт 3,00"], "standard 2,50": ["standard 2.50", "стандарт 2,50"],
  "em peça": ["in a piece", "у деталі"], "cores:": ["colours:", "кольори:"],
  "tracejados": ["hatched", "заштриховані"], "rejeitados": ["rejected", "відхилені"],
  "Painel produzido à largura pedida": ["Panel made to the requested width", "Панель виготовляється на потрібну ширину"],
  "Calcular juntas, corte e 3D": ["Calculate joints, cutting and 3D", "Розрахувати вузли, розкрій і 3D"],
  "A calcular…": ["Calculating…", "Розрахунок…"],
  "Modelo IFC": ["IFC model", "Модель IFC"], "Desenhos PDF": ["PDF drawings", "Креслення PDF"], "Desenhos DXF": ["DXF drawings", "Креслення DXF"],
  "Volume das peças = união das plantas (GEOS)": ["Piece volume = union of plan outlines (GEOS)", "Об'єм деталей = об'єднання контурів (GEOS)"],
  "Volume 3D OpenCascade = analítico": ["OpenCascade 3D volume = analytic", "3D-об'єм OpenCascade = аналітичний"],
  "painéis de prensa": ["press panels", "пресових панелей"],
  "desperdício": ["waste", "відходи"], "juntas verticais": ["vertical joints", "вертикальні вузли"],
  "contagem dupla evitada": ["double count avoided", "уникнуто подвійного підрахунку"],
  "painéis": ["panels", "панелей"], "mínimo teórico": ["theoretical minimum", "теоретичний мінімум"],
  "Painel": ["Panel", "Панель"], "aproveitamento": ["yield", "використання"],
  "Formato:": ["Format:", "Формат:"], "Corte de serra:": ["Saw kerf:", "Пропил:"],
  "O modelo não passou a verificação de volumes.": ["The model failed the volume check.", "Модель не пройшла перевірку об'ємів."],
  "Verifique o ficheiro e os valores.": ["Check the file and the values.", "Перевірте файл і значення."],
  // costs workspace
  "Calcular custo total": ["Calculate total cost", "Розрахувати загальну вартість"],
  "Bibliotecas": ["Libraries", "Бібліотеки"],
  "Pisos preenchidos a partir do último PDF lido: paredes medidas, altura estrutural do corte, laje, cobertura, lintéis, painéis sobre portas, teto BA15, vigas de aço e revestimentos (BA13 duplo e pintura nas faces interiores, como no corte). Confirme antes de orçamentar.": [
    "Floors filled from the last PDF read: measured walls, structural height from the section, slab, roof, lintels, panels over doors, BA15 ceiling, steel beams and linings (double BA13 and paint on the interior faces, as in the section). Confirm before pricing.",
    "Поверхи заповнено з останнього зчитаного PDF: обміряні стіни, конструктивна висота з розрізу, перекриття, покрівля, перемички, панелі над дверима, стеля BA15, сталеві балки та облицювання (подвійний BA13 і фарбування внутрішніх граней, як у розрізі). Перевірте перед кошторисом."],
  "Data de início": ["Start date", "Дата початку"], "Começar o plano em": ["Start the plan at", "Почати план з"],
  "Compra da matéria-prima": ["Raw material purchase", "Закупівля сировини"], "Início do fabrico": ["Start of fabrication", "Початок виготовлення"],
  "IVA da venda": ["VAT on sale", "ПДВ на продаж"],
  "Portugal · 23 % (CIVA art. 18.º)": ["Portugal · 23 % (CIVA art. 18)", "Португалія · 23 % (CIVA ст. 18)"],
  "Ucrânia · ПДВ 20 % (ПКУ ст. 193.1)": ["Ukraine · VAT 20 % (Tax Code art. 193.1)", "Україна · ПДВ 20 % (ПКУ ст. 193.1)"],
  "Exportação da Ucrânia · 0 % (ПКУ ст. 195.1.1)": ["Export from Ukraine · 0 % (Tax Code art. 195.1.1)", "Експорт з України · 0 % (ПКУ ст. 195.1.1)"],
  "Altura estrutural (m)": ["Structural height (m)", "Конструктивна висота (м)"],
  "Vazio = altura standard da empresa (RDC 3,00 m, outros pisos 2,50 m), editável nos parâmetros": [
    "Empty = company standard height (ground floor 3.00 m, other floors 2.50 m), editable in the parameters",
    "Порожньо = стандартна висота компанії (перший поверх 3,00 м, інші 2,50 м), змінюється в параметрах"],
  "Espessura (mm)": ["Thickness (mm)", "Товщина (мм)"], "Camadas (juntas coladas + 1)": ["Layers (glued joints + 1)", "Шари (клейові шви + 1)"],
  "Adicionar espessura": ["Add thickness", "Додати товщину"], "Adicionar laje, cobertura ou lintel": ["Add slab, roof or lintel", "Додати перекриття, покрівлю або перемичку"],
  "Adicionar piso": ["Add floor", "Додати поверх"], "Retirar elemento": ["Remove element", "Прибрати елемент"],
  "Área (m²)": ["Area (m²)", "Площа (м²)"],
  "Placa de gesso (m², somando camadas)": ["Plasterboard (m², all layers)", "Гіпсокартон (м², сума шарів)"], "Pintura (m²)": ["Paint (m²)", "Фарбування (м²)"],
  "Teto falso BA15 (m²)": ["BA15 suspended ceiling (m²)", "Підвісна стеля BA15 (м²)"],
  "Laje: membrana e betão leve (m²)": ["Slab: membrane and lightweight screed (m²)", "Перекриття: мембрана та легка стяжка (м²)"],
  "Cobertura plana: isolamento e impermeabilização (m²)": ["Flat roof: insulation and waterproofing (m²)", "Пласка покрівля: утеплення та гідроізоляція (м²)"],
  "Face exterior das paredes (m²)": ["Exterior wall face (m²)", "Зовнішня грань стін (м²)"], "Vigas de aço (m)": ["Steel beams (m)", "Сталеві балки (м)"],
  "Laje": ["Slab", "Перекриття"], "Cobertura": ["Roof", "Покрівля"], "Lintel": ["Lintel", "Перемичка"], "Painel sobre vão": ["Panel over opening", "Панель над отвором"],
  "Vãos exteriores:": ["Exterior openings:", "Зовнішні отвори:"], "sob": ["under", "під"],
  "Criar lote de seguimento com este plano": ["Create a tracking package with this plan", "Створити пакет контролю з цим планом"],
  "Custo total": ["Total cost", "Загальна вартість"], "Venda": ["Sale", "Продаж"], "Margem": ["Margin", "Маржа"],
  "m³ fabrico": ["m³ fabrication", "м³ виготовлення"], "m² montagem": ["m² assembly", "м² монтажу"],
  "h fabrico": ["h fabrication", "год виготовлення"], "h montagem": ["h assembly", "год монтажу"],
  "Detalhe por preço da biblioteca": ["Detail by library price", "Деталізація за цінами бібліотеки"],
  "Código": ["Code", "Код"], "Designação": ["Description", "Найменування"], "Quantidade": ["Quantity", "Кількість"],
  "Custo": ["Cost", "Вартість"], "Origem": ["Source", "Джерело"], "Início": ["Start", "Початок"], "entrega montada": ["assembled handover", "здача змонтованого"],
  "dias": ["days", "днів"], "Estimativa com": ["Estimate with", "Кошторис із"], "valores por confirmar:": ["values to confirm:", "значеннями для підтвердження:"],
  "criado. O avanço segue-se no separador Custos e avanço.": ["created. Progress is tracked in the Costs and progress tab.", "створено. Прогрес відстежується на вкладці «Витрати та прогрес»."],
  // parameters and libraries
  "Alturas standard (planta sem alturas)": ["Standard heights (plan without heights)", "Стандартні висоти (план без висот)"],
  "Fabrico": ["Fabrication", "Виготовлення"], "Transporte": ["Transport", "Транспорт"], "Montagem em obra": ["Site assembly", "Монтаж на об'єкті"],
  "Prazos": ["Lead times", "Терміни"], "Venda e impostos": ["Sale and taxes", "Продаж і податки"],
  "Empresa": ["Company", "Компанія"], "Média de mercado": ["Market average", "Середнє по ринку"], "Hipótese por confirmar": ["Hypothesis to confirm", "Припущення для підтвердження"],
  "Guardar parâmetros técnicos": ["Save technical parameters", "Зберегти технічні параметри"], "Guardar": ["Save", "Зберегти"],
  "Colar do Excel ou importar ficheiro (Excel, CSV, PDF)": ["Paste from Excel or import a file (Excel, CSV, PDF)", "Вставити з Excel або імпортувати файл (Excel, CSV, PDF)"],
  "Cole aqui as células do Excel": ["Paste the Excel cells here", "Вставте сюди клітинки з Excel"],
  "Colunas: Categoria, Código, Designação, Unidade, Custo, Venda, Base, Consumo por base, Fonte. Copie as linhas no Excel com o cabeçalho e cole aqui.": [
    "Columns: Category, Code, Description, Unit, Cost, Sale, Basis, Use per basis, Source. Copy the rows in Excel with the header and paste here.",
    "Стовпці: Категорія, Код, Найменування, Одиниця, Вартість, Продаж, База, Витрата на базу, Джерело. Скопіюйте рядки в Excel із заголовком і вставте сюди."],
  "Descarregar modelo": ["Download template", "Завантажити шаблон"], "Importar ficheiro": ["Import file", "Імпортувати файл"],
  "Guardar estes preços": ["Save these prices", "Зберегти ці ціни"], "preços reconhecidos": ["prices recognised", "цін розпізнано"],
  "linhas com erro": ["rows with errors", "рядків з помилками"], "Linha": ["Row", "Рядок"],
  "Adicionar preço": ["Add price", "Додати ціну"], "Unidade": ["Unit", "Одиниця"], "Custo (€)": ["Cost (€)", "Вартість (€)"], "Venda (€)": ["Sale (€)", "Продаж (€)"],
  "Quantidade por base": ["Quantity per basis", "Кількість на базу"], "por base": ["per basis", "на базу"], "Em vigor desde": ["Valid from", "Діє з"],
  "Atualizar eletricidade (Eurostat)": ["Update electricity (Eurostat)", "Оновити електроенергію (Eurostat)"],
  "Escalão de consumo anual": ["Annual consumption band", "Діапазон річного споживання"], "Tabela": ["Table", "Таблиця"],
  // packages and rates
  "Novo lote": ["New package", "Новий пакет"], "Nome do lote": ["Package name", "Назва пакета"], "Nome": ["Name", "Назва"],
  "Receita contratada (€)": ["Contracted revenue (€)", "Договірний дохід (€)"], "Entrega contratada": ["Contracted delivery", "Договірна здача"],
  "Entrega prevista": ["Forecast delivery", "Прогнозна здача"], "Artigo": ["Item", "Позиція"], "Fase": ["Stage", "Етап"],
  "Código do artigo": ["Item code", "Код позиції"], "Custo unitário (€)": ["Unit cost (€)", "Ціна за одиницю (€)"],
  "Quantidade orçamentada": ["Budgeted quantity", "Кошторисна кількість"], "Quantidade prevista até hoje": ["Quantity planned to date", "Запланована кількість на сьогодні"],
  "Quantidade aceite": ["Accepted quantity", "Прийнята кількість"], "Custo real (€)": ["Actual cost (€)", "Фактична вартість (€)"],
  "Compromisso em aberto (€)": ["Open commitment (€)", "Відкриті зобов'язання (€)"], "Previsão não contratada (€)": ["Uncommitted forecast (€)", "Неузгоджений прогноз (€)"],
  "Origem da quantidade": ["Quantity source", "Джерело кількості"], "Referência do custo real": ["Actual cost reference", "Посилання на фактичну вартість"],
  "Tarifa da biblioteca": ["Library rate", "Тариф бібліотеки"], "Introduzir custo unitário": ["Enter unit cost", "Ввести ціну за одиницю"],
  "Tarifa guardada": ["Saved rate", "Збережений тариф"], "Adicionar artigo": ["Add item", "Додати позицію"], "Retirar artigo": ["Remove item", "Прибрати позицію"],
  "Guardar revisão": ["Save revision", "Зберегти ревізію"], "Revisão": ["Revision", "Ревізія"], "guardada": ["saved", "збережено"],
  "Real": ["Actual", "Факт"], "Desvio": ["Deviation", "Відхилення"], "Margem prevista": ["Forecast margin", "Прогнозна маржа"],
  "Entrega:": ["Handover:", "Здача:"], "dias de desvio": ["days of delay", "днів відхилення"], "Aceite": ["Accepted", "Прийнято"], "Previsto": ["Planned", "Заплановано"],
  "Compra": ["Purchase", "Закупівля"], "Produção": ["Production", "Виробництво"], "Montagem": ["Assembly", "Монтаж"], "Entrega": ["Handover", "Здача"],
  "Revestimentos e isolamentos": ["Linings and insulation", "Облицювання та утеплення"], "Instalações e acabamentos": ["Services and finishes", "Інженерні мережі та оздоблення"],
  "Engenharia e indiretos": ["Engineering and indirect costs", "Проєктування та непрямі витрати"],
  "Guardar nova tarifa": ["Save new rate", "Зберегти новий тариф"], "Valor unitário (€)": ["Unit value (€)", "Значення за одиницю (€)"], "Descrição": ["Description", "Опис"],
  "Custos CLT": ["CLT costs", "Витрати CLT"],
};

// Texts with numbers: [regex, [en, uk]] with $1… for the captured parts.
const PATTERNS = [
  [/^Piso (\d+)$/, ["Floor $1", "Поверх $1"]],
  [/^Artigo (\d+)$/, ["Item $1", "Позиція $1"]],
  [/^(\d+) dias de desvio$/, ["$1 days of delay", "$1 днів відхилення"]],
  [/^(\d+) preços guardados\.$/, ["$1 prices saved.", "$1 цін збережено."]],
  [/^(.+) guardado\.$/, ["$1 saved.", "$1 збережено."]],
  [/^Linha (\d+):/, ["Row $1:", "Рядок $1:"]],
  [/^escala 1:(\d+) lida na folha$/, ["scale 1:$1 read on the sheet", "масштаб 1:$1 зчитано з аркуша"]],
  [/^escala 1:(\d+) indicada pelo utilizador(.*)$/, ["scale 1:$1 given by the user$2", "масштаб 1:$1 вказано користувачем$2"]],
  [/^hipótese editável \(largura de serra\/fresa\)$/, ["editable hypothesis (saw/router width)", "припущення, можна змінити (ширина пили/фрези)"]],
];

const ATTRS = ["placeholder", "title", "aria-label"];
const original = new WeakMap();
const originalAttr = new WeakMap();

function translateText(text, lang, dict) {
  const key = text.replace(/\s+/g, " ").trim();
  if (!key) return null;
  const i = lang === "en" ? 0 : 1;
  if (UI[key]) return UI[key][i];
  if (dict && typeof dict[key] === "string") return dict[key];
  for (const [re, out] of PATTERNS) {
    if (re.test(key)) return key.replace(re, out[i]);
  }
  return null;
}

function apply(root, lang, dict) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (node.parentElement?.closest("textarea, input, [data-no-clt-translate]")) continue;
    if (!original.has(node)) original.set(node, node.nodeValue);
    const source = original.get(node);
    // the page changed this node since it was translated: take the new text as the source
    const current = node.nodeValue;
    if (current !== source && current !== node.__cltOut) original.set(node, current);
    const base = original.get(node);
    const out = lang === "pt" ? base : translateText(base, lang, dict);
    const next = out == null ? base : base.replace(base.trim(), out);
    if (node.nodeValue !== next) node.nodeValue = next;
    node.__cltOut = next;
  }
  for (const el of root.querySelectorAll("[placeholder],[title],[aria-label]")) {
    const saved = originalAttr.get(el) || {};
    for (const a of ATTRS) {
      const v = el.getAttribute(a);
      if (v == null) continue;
      if (!(a in saved) || (v !== saved[a] && v !== saved[`${a}__out`])) saved[a] = v;
      const out = lang === "pt" ? saved[a] : translateText(saved[a], lang, dict) ?? saved[a];
      if (v !== out) el.setAttribute(a, out);
      saved[`${a}__out`] = out;
    }
    originalAttr.set(el, saved);
  }
}

// Translates its subtree to lang (pt | en | uk) and keeps it translated while React re-renders.
export function LangScope({ lang, dict, children, className }) {
  const ref = useRef(null);
  useEffect(() => {
    const root = ref.current;
    if (!root) return undefined;
    let scheduled = false;
    const run = () => { scheduled = false; observer.disconnect(); apply(root, lang, dict); observer.observe(root, OPTIONS); };
    const observer = new MutationObserver(() => { if (!scheduled) { scheduled = true; requestAnimationFrame(run); } });
    const OPTIONS = { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS };
    run();
    return () => observer.disconnect();
  }, [lang, dict]);
  // translate="no": the app-wide translator must not translate this page a second time
  return <div ref={ref} className={className} translate={lang === "pt" ? undefined : "no"} data-no-translate={lang === "pt" ? undefined : ""}>{children}</div>;
}

export function initialCltLang(user) {
  try {
    const saved = localStorage.getItem("cp_clt_lang");
    if (saved && saved in CLT_LANGS) return saved;
  } catch { /* storage unavailable */ }
  const langs = Array.isArray(user?.doc_langs) ? user.doc_langs : [];
  return langs.includes("uk") ? "uk" : "pt";
}

export function rememberCltLang(lang) {
  try { localStorage.setItem("cp_clt_lang", lang); } catch { /* storage unavailable */ }
}
