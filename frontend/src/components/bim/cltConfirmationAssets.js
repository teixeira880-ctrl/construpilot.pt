// Shared CLT review template and runtime. Keep in sync with the local preview.
export const confirmationTemplate = String.raw`<section id="home-a-confirm" aria-label="Home A, confirmação de medições">
  <style>
    #home-a-confirm { display:grid; gap:12px; }
    #home-a-confirm [hidden] { display:none !important; }
    #home-a-confirm .layout { display:grid; grid-template-columns:minmax(0,1.25fr) minmax(0,1fr); gap:16px; align-items:start; }
    #home-a-confirm .sheet { position:relative; }
    #home-a-confirm .sheet img { display:block; width:100%; height:auto; }
    #home-a-confirm .mark { position:absolute; border:1px solid var(--orange); background:color-mix(in srgb,var(--orange) 18%,transparent); pointer-events:none; }
    #home-a-confirm .mark[data-kind=measured] { border-color:var(--green); background:color-mix(in srgb,var(--green) 18%,transparent); }
    #home-a-confirm .mark[data-kind=declared] { border-color:var(--blue); background:color-mix(in srgb,var(--blue) 18%,transparent); }
    #home-a-confirm .mark.selected { outline:3px solid var(--primary); outline-offset:1px; z-index:2; }
    #home-a-confirm .mark.confirmed { border-width:2px; background:color-mix(in srgb,var(--green) 40%,transparent); }
    #home-a-confirm .controls, #home-a-confirm form, #home-a-confirm .saved { display:grid; gap:10px; min-width:0; }
    #home-a-confirm .pair { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
    #home-a-confirm form { margin:0; }
    #home-a-confirm fieldset { border:0; padding:0; margin:0; min-width:0; }
    #home-a-confirm .list { margin:0; padding-left:20px; overflow-wrap:anywhere; }
    #home-a-confirm output { display:block; font-variant-numeric:tabular-nums; }
    @media(max-width:680px) { #home-a-confirm .layout { grid-template-columns:minmax(0,1fr); } }
    @media(max-width:400px) { #home-a-confirm .pair { grid-template-columns:minmax(0,1fr); } }
  </style>
  <div class="viz-row">
    <h2>Home A · Confirmação de medições</h2>
    <label class="form-label">Folha <select class="form-select" data-page></select></label>
  </div>
  <div class="table-responsive">
    <table class="table table-sm">
      <thead><tr><th scope="col">Piso</th><th scope="col">CLT em planta</th><th scope="col">Volume CLT confirmado</th><th scope="col">Área de revestimento confirmada</th></tr></thead>
      <tbody data-totals></tbody>
    </table>
  </div>
  <div class="viz-row text-small">
    <span>🟢 Traçado medido</span><span>🔵 Área declarada</span><span>🟠 Referência a verificar</span>
  </div>
  <div class="layout">
    <div class="sheet">
      <img alt="Folha do Home A">
      <div data-marks aria-hidden="true"></div>
    </div>
    <div class="controls">
      <label class="form-label">Localizar no desenho <select class="form-select" data-reference></select></label>
      <p data-detail aria-live="polite"></p>
      <div class="viz-row" data-modes hidden>
        <button class="btn btn-secondary" type="button" data-mode="clt" aria-pressed="true">Volume CLT</button>
        <button class="btn btn-secondary" type="button" data-mode="finish" aria-pressed="false">Revestimento</button>
      </div>
      <form data-clt hidden>
        <div class="pair">
          <label class="form-label">Altura estrutural (mm)<input class="form-control" name="height" inputmode="decimal" required></label>
          <label class="form-label">Espessura CLT (mm)<input class="form-control" name="thickness" inputmode="decimal" required></label>
        </div>
        <label class="form-label">Área dos recortes passantes ainda incluídos no troço (m²)<input class="form-control" name="deduction" inputmode="decimal" required></label>
        <p class="text-small">Escreve 0 só se confirmaste que não há recortes a descontar. Exclui vãos já fora do contorno.</p>
        <label class="form-label">Referência da confirmação <input class="form-control" name="source" placeholder="Folha ou corte, eixo e cota" maxlength="100" required></label>
        <output data-clt-calc aria-live="polite"></output>
        <div class="viz-row"><button class="btn btn-primary">Confirmar volume</button><button class="btn btn-secondary" type="button" data-remove-clt hidden>Retirar confirmação</button></div>
      </form>
      <form data-finish hidden>
        <div class="pair">
          <label class="form-label">Material / camada <input class="form-control" name="material" placeholder="Ex.: gesso cartonado" maxlength="45" required></label>
          <label class="form-label">Face <select class="form-select" name="face" required></select></label>
        </div>
        <fieldset data-wall>
          <div class="pair">
            <label class="form-label">Altura revestida (mm)<input class="form-control" name="height" inputmode="decimal"></label>
            <label class="form-label">Descontos na faixa (m²)<input class="form-control" name="deduction" inputmode="decimal"></label>
          </div>
        </fieldset>
        <fieldset data-room hidden>
          <label class="form-label">Área revestida confirmada (m²)<input class="form-control" name="area" inputmode="decimal"></label>
          <button class="btn btn-secondary" type="button" data-use-area>Usar área declarada</button>
        </fieldset>
        <label class="form-label">Referência da aplicação <input class="form-control" name="source" placeholder="Folha, divisão e face a revestir" maxlength="100" required></label>
        <output data-finish-calc aria-live="polite"></output>
        <button class="btn btn-primary">Confirmar revestimento</button>
      </form>
      <p data-message role="status"></p>
      <div class="saved">
        <h3>Confirmações nesta folha</h3>
        <div data-records></div>
      </div>
    </div>
  </div>
  <script type="application/json" id="home-a-confirm-data">__EVIDENCE_PAYLOAD__</script>
  <script>__CONFIRMATION_SCRIPT__</script>
</section>
`;
export const confirmationScript = String.raw`(() => {
  const root = document.getElementById("home-a-confirm");
  const pages = JSON.parse(document.getElementById("home-a-confirm-data").textContent);
  const get = (selector) => root.querySelector(selector);
  const sheet = get("[data-page]");
  const picker = get("[data-reference]");
  const image = get("img");
  const marks = get("[data-marks]");
  const detail = get("[data-detail]");
  const clt = get("[data-clt]");
  const finish = get("[data-finish]");
  const messages = get("[data-message]");
  const faces = finish.elements.face;
  const nf = new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 4 });
  const kindName = { opening_dimensions: "Vão", ceiling_height: "Pé-direito", material_note: "Material", declared_area: "Área declarada" };
  const faceName = { a: "Parede · face A", b: "Parede · face B", floor: "Pavimento", ceiling: "Teto" };
  let state = { volumes: [], finishes: [] };
  let mode = "clt";
  let editingFinish = null;

  const currentPage = () => pages[Number(sheet.value) - 1];
  function references(page) {
    const evidence = new Map(page.evidence.map((item) => [item.id, item]));
    const refs = new Map((page.review?.markers || []).map((item) => [item.id, { ...evidence.get(item.id), ...item }]));
    for (const item of evidence.values()) {
      if (!refs.has(item.id)) refs.set(item.id, { ...item, status: "pending" });
    }
    return refs;
  }
  const selected = () => references(currentPage()).get(picker.value);
  const isTroco = (item) => Number.isFinite(item?.length_m) && item.length_m > 0;
  const isRoom = (page, item) => page.page === 1 && item?.kind === "declared_area";
  const display = (value, unit) => nf.format(value) + " " + unit;
  const keyOf = (page, item) => page.page + ":" + item.id;
  const getInput = (form, name) => form.elements.namedItem(name);
  const valueOf = (form, name) => getInput(form, name).value.trim();
  const safeSource = (value) => typeof value === "string" && value.trim().length > 0 && value.length <= 100;
  const safeMaterial = (value) => typeof value === "string" && value.trim().length > 0 && value.length <= 45;

  function number(value) {
    if (typeof value === "number") return Number.isFinite(value) ? value : null;
    if (!/^\d+(?:[.,]\d{1,6})?$/.test(value)) return null;
    const result = Number(value.replace(",", "."));
    return Number.isFinite(result) ? result : null;
  }
  function dimensions(height, deduction) {
    return height !== null && height > 0 && height <= 100000 && deduction !== null && deduction >= 0;
  }
  function cltVolume(item, row) {
    const { height, thickness, deduction } = row;
    if (!isTroco(item) || !dimensions(height, deduction) || thickness === null || thickness <= 0 || thickness > 1500) return null;
    const grossFace = item.length_m * height / 1000;
    return deduction >= grossFace ? null : (grossFace - deduction) * thickness / 1000;
  }
  function finishArea(page, item, row) {
    if (isRoom(page, item) && ["floor", "ceiling"].includes(row.face)) {
      return row.area !== null && row.area > 0 && row.area <= item.values[0] ? row.area : null;
    }
    if (!isTroco(item) || !["a", "b"].includes(row.face) || !dimensions(row.height, row.deduction)) return null;
    const grossFace = item.length_m * row.height / 1000;
    return row.deduction >= grossFace ? null : grossFace - row.deduction;
  }
  function sourceByKey(key) {
    const [pageNo, id] = String(key).split(":");
    const page = pages[Number(pageNo) - 1];
    return page ? [page, references(page).get(id)] : [null, null];
  }
  function formatRef(item) {
    if (item.label) return item.label;
    return (kindName[item.kind] || "Referência") + " · " + item.text.replaceAll("m�", "m²");
  }
  function normalMaterial(material) {
    return material.trim().normalize("NFC").toLocaleLowerCase("pt-PT").replace(/\s+/g, " ");
  }
  function finishKey(row) {
    return [row.key, row.face, normalMaterial(row.material)].join("|");
  }
  function restore(snapshot) {
    const data = snapshot?.privateContent;
    if (!data || data.version !== 1 || !Array.isArray(data.volumes) || !Array.isArray(data.finishes)) return;
    const volumes = new Map(), finishes = new Map();
    for (const row of data.volumes) {
      if (!row || !safeSource(row.source)) continue;
      const [, item] = sourceByKey(row.key);
      const clean = { key: row.key, height: number(row.height), thickness: number(row.thickness),
        deduction: number(row.deduction), source: row.source };
      if (cltVolume(item, clean) !== null) volumes.set(row.key, clean);
    }
    for (const row of data.finishes) {
      if (!row || !safeSource(row.source) || !safeMaterial(row.material)) continue;
      const [page, item] = sourceByKey(row.key);
      const clean = { key: row.key, face: row.face, material: row.material, height: number(row.height),
        deduction: number(row.deduction), area: number(row.area), source: row.source };
      if (page && finishArea(page, item, clean) !== null) finishes.set(finishKey(clean), clean);
    }
    state = { volumes: [...volumes.values()], finishes: [...finishes.values()] };
  }
  function floorTotals(page) {
    const refs = references(page);
    const idPrefix = page.page + ":";
    const volumeRows = state.volumes.filter((row) => row.key.startsWith(idPrefix));
    const finishRows = state.finishes.filter((row) => row.key.startsWith(idPrefix));
    const volume = volumeRows.reduce((total, row) => total + cltVolume(refs.get(row.key.split(":")[1]), row), 0);
    const area = finishRows.reduce((total, row) => total + finishArea(page, refs.get(row.key.split(":")[1]), row), 0);
    return { piso: page.review.floor, clt_plant_m2: page.review.clt_plan_m2,
      volume_m3: volumeRows.length ? volume : null,
      segmentos_confirmados: volumeRows.length, segmentos_medidos: [...refs.values()].filter(isTroco).length,
      revestimento_m2: finishRows.length ? area : null, aplicacoes_confirmadas: finishRows.length };
  }
  function store(next) {
    const privateContent = { version: 1, ...next };
    if (new TextEncoder().encode(JSON.stringify(privateContent)).length > 13500) {
      messages.textContent = "A beta atingiu o limite de confirmações que pode guardar nesta conversa.";
      return false;
    }
    state = next;
    const modelContent = { home_a: pages.slice(0, 3).map(floorTotals) };
    window.openai?.setWidgetState?.({ privateContent, modelContent })?.catch(() => {});
    return true;
  }
  function renderTotals() {
    const rows = pages.slice(0, 3).map((page) => {
      const totals = floorTotals(page);
      const tr = document.createElement("tr");
      const vals = [totals.piso,
        totals.clt_plant_m2 === null ? "Por medir" : display(totals.clt_plant_m2, "m²"),
        totals.volume_m3 === null ? "Por confirmar" : display(totals.volume_m3, "m³") + " · " +
          totals.segmentos_confirmados + "/" + totals.segmentos_medidos + " troços medidos",
        totals.revestimento_m2 === null ? "Por confirmar" : display(totals.revestimento_m2, "m²") + " · " +
          totals.aplicacoes_confirmadas + (totals.aplicacoes_confirmadas === 1 ? " aplicação" : " aplicações")];
      vals.forEach((value, index) => {
        const cell = document.createElement(index ? "td" : "th");
        if (!index) cell.scope = "row";
        cell.textContent = value;
        tr.append(cell);
      });
      return tr;
    });
    get("[data-totals]").replaceChildren(...rows);
  }
  function paint() {
    const page = currentPage();
    const active = selected();
    const confirmations = new Set([...state.volumes, ...state.finishes].map((row) => row.key));
    marks.replaceChildren(...[...references(page).values()].map((item) => {
      const [x, y, right, bottom] = item.rect;
      const mark = document.createElement("span");
      mark.className = "mark";
      mark.dataset.kind = item.status;
      mark.dataset.ref = item.id;
      mark.classList.toggle("selected", item.id === active?.id);
      mark.classList.toggle("confirmed", confirmations.has(keyOf(page, item)));
      Object.assign(mark.style, { left: x * 100 + "%", top: y * 100 + "%",
        width: (right - x) * 100 + "%", height: (bottom - y) * 100 + "%" });
      return mark;
    }));
  }
  function readClt() {
    return { height: number(valueOf(clt, "height")), thickness: number(valueOf(clt, "thickness")),
      deduction: number(valueOf(clt, "deduction")), source: valueOf(clt, "source") };
  }
  function readFinish() {
    return { face: faces.value, material: valueOf(finish, "material"), height: number(valueOf(finish, "height")),
      deduction: number(valueOf(finish, "deduction")), area: number(valueOf(finish, "area")),
      source: valueOf(finish, "source") };
  }
  function live() {
    const item = selected();
    const volume = cltVolume(item, readClt());
    const area = finishArea(currentPage(), item, readFinish());
    get("[data-clt-calc]").textContent = volume === null ? "Preenche as três medidas confirmadas." : "Volume calculado: " + display(volume, "m³");
    get("[data-finish-calc]").textContent = area === null ? "Preenche a face e as medidas confirmadas." : "Área calculada: " + display(area, "m²");
  }
  function updateModes() {
    const item = selected();
    const room = isRoom(currentPage(), item);
    get("[data-modes]").hidden = !isTroco(item);
    clt.hidden = !(isTroco(item) && mode === "clt");
    finish.hidden = !room && !(isTroco(item) && mode === "finish");
    for (const button of root.querySelectorAll("[data-mode]")) button.setAttribute("aria-pressed", String(button.dataset.mode === mode));
    get("[data-wall]").hidden = room;
    get("[data-room]").hidden = !room;
  }
  function recordButton(label, click) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-secondary";
    button.textContent = label;
    button.addEventListener("click", click);
    return button;
  }
  function fill(form, row) {
    for (const input of form.elements) {
      if (input.name && row[input.name] != null) input.value = String(row[input.name]).replace(
        /^(?=\d+\.\d+$)(\d+)\.(\d+)$/, "$1,$2");
    }
  }
  function renderSaved() {
    const page = currentPage(), refs = references(page);
    const list = document.createElement("ul");
    list.className = "list";
    const prefix = page.page + ":";
    for (const row of [...state.volumes, ...state.finishes].filter((item) => item.key.startsWith(prefix))) {
      const id = row.key.slice(prefix.length);
      const ref = refs.get(id);
      const li = document.createElement("li");
      li.textContent = row.material ? row.material + " · " + faceName[row.face] + " · " +
        display(finishArea(page, ref, row), "m²") : formatRef(ref) + " · " + display(cltVolume(ref, row), "m³");
      const citation = document.createElement("small");
      citation.textContent = " · " + row.source + " ";
      li.append(citation, recordButton("Editar", () => {
        picker.value = id;
        onReference();
        if (row.material) {
          mode = "finish";
          editingFinish = finishKey(row);
          updateModes();
          fill(finish, row);
          live();
          getInput(finish, "material").focus();
        } else {
          getInput(clt, "height").focus();
        }
      }), recordButton("Retirar", () => {
        const next = row.material ? { ...state, finishes: state.finishes.filter((r) => finishKey(r) !== finishKey(row)) }
          : { ...state, volumes: state.volumes.filter((r) => r.key !== row.key) };
        if (store(next)) { onReference(); messages.textContent = "Confirmação retirada."; }
      }));
      list.append(li);
    }
    get("[data-records]").replaceChildren(list.childElementCount ? list : document.createTextNode("Ainda sem confirmações nesta folha."));
  }
  function onReference() {
    const page = currentPage();
    const item = selected();
    clt.reset();
    finish.reset();
    editingFinish = null;
    mode = isTroco(item) ? "clt" : "finish";
    messages.textContent = "";
    const row = item && state.volumes.find((volume) => volume.key === keyOf(page, item));
    if (row) fill(clt, row);
    get("[data-remove-clt]").hidden = !row;
    const room = isRoom(page, item);
    faces.replaceChildren(...(room ? ["", "floor", "ceiling"] : ["", "a", "b"])
      .map((face) => new Option(faceName[face] || "Selecionar", face)));
    detail.textContent = !item ? "Seleciona um troço, área ou cota para o assinalar." :
      isTroco(item) ? "Comprimento medido: " + display(item.length_m, "m") + ". Largura gráfica: " +
        display(item.drawing_width_mm, "mm") + ". Confirma a espessura e a altura no pormenor." :
      room ? formatRef(item) + ". Confirma se a área se aplica ao pavimento ou ao teto escolhido." :
      item.kind === "opening_dimensions" ? formatRef(item) + " · " + display(item.values[0] * item.values[1] / 1e6, "m²") + ". Associa o vão ao troço antes de o descontar." :
      item.kind === "ceiling_height" ? formatRef(item) + ". Esta cota é um pé-direito de acabamento." : formatRef(item);
    updateModes();
    paint();
    live();
    renderTotals();
    renderSaved();
  }
  function onSheet() {
    const page = currentPage();
    image.src = page.image;
    image.alt = page.label;
    picker.replaceChildren(new Option("Selecionar referência", ""), ...[...references(page).values()]
      .map((item) => new Option(formatRef(item), item.id)));
    onReference();
  }
  clt.addEventListener("submit", (event) => {
    event.preventDefault();
    const item = selected(), row = readClt();
    const result = cltVolume(item, row);
    if (result === null || !safeSource(row.source)) {
      messages.textContent = "Confirma altura, espessura, recortes e fonte. O desconto tem de ser menor do que a face do troço.";
      return;
    }
    row.key = keyOf(currentPage(), item);
    if (store({ ...state, volumes: [...state.volumes.filter((r) => r.key !== row.key), row] })) {
      onReference();
      messages.textContent = "Volume confirmado: " + display(result, "m³") + ".";
    }
  });
  finish.addEventListener("submit", (event) => {
    event.preventDefault();
    const page = currentPage(), item = selected(), row = readFinish();
    const result = finishArea(page, item, row);
    if (result === null || !safeMaterial(row.material) || !safeSource(row.source)) {
      messages.textContent = "Indica o material, a face, uma área válida e a referência. Confirma também os descontos se for uma parede.";
      return;
    }
    row.key = keyOf(page, item);
    const id = finishKey(row);
    if (state.finishes.some((r) => finishKey(r) === id && finishKey(r) !== editingFinish)) {
      messages.textContent = "Já existe este material nesta face. Edita a confirmação existente para a corrigir.";
      return;
    }
    if (store({ ...state, finishes: [...state.finishes.filter((r) => finishKey(r) !== editingFinish), row] })) {
      onReference();
      mode = "finish";
      updateModes();
      messages.textContent = "Área de revestimento confirmada: " + display(result, "m²") + ".";
    }
  });
  get("[data-remove-clt]").addEventListener("click", () => {
    const key = keyOf(currentPage(), selected());
    if (store({ ...state, volumes: state.volumes.filter((row) => row.key !== key) })) {
      onReference();
      messages.textContent = "Confirmação retirada.";
    }
  });
  get("[data-use-area]").addEventListener("click", () => {
    const item = selected();
    if (!isRoom(currentPage(), item)) return;
    getInput(finish, "area").value = String(item.values[0]).replace(".", ",");
    live();
  });
  for (const button of root.querySelectorAll("[data-mode]")) button.addEventListener("click", () => {
    mode = button.dataset.mode;
    messages.textContent = "";
    updateModes();
  });
  for (const page of pages) sheet.add(new Option(page.label, page.page));
  clt.addEventListener("input", live);
  finish.addEventListener("input", live);
  sheet.addEventListener("change", onSheet);
  picker.addEventListener("change", onReference);
  window.addEventListener("openai:set_globals", (event) => {
    restore(event.detail?.globals?.widgetState);
    onReference();
  });
  restore(window.openai?.widgetState);
  onSheet();
})();
`;
