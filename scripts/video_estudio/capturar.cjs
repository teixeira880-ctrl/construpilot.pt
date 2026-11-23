const { chromium } = require("/home/claude/fe-build/node_modules/playwright-core");
(async () => {
  const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome", headless: true,
    args: ["--no-sandbox", "--no-proxy-server", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  const erros = []; page.setDefaultTimeout(8000);
  page.on("pageerror", (e) => erros.push(e.message));
  page.on("dialog", (d) => d.accept("Pavimento radiante"));
  await page.goto("http://127.0.0.1:8766/", { waitUntil: "networkidle" });
  await page.waitForSelector('[data-testid="estudio-planta"]');
  await page.waitForTimeout(1500);
  const shot = async (n) => { await page.waitForTimeout(500); await page.screenshot({ path: `/home/claude/video/cap/${n}.jpg`, type: "jpeg", quality: 92 }); };
  const topo = async () => { await page.evaluate(() => window.scrollTo(0, 0)); };
  const verAbas = async () => { await page.evaluate(() => { const e = document.querySelector('[data-testid="estudio-aba-3d"]'); window.scrollTo(0, e.getBoundingClientRect().top + window.scrollY - 12); }); };
  const T = (t) => `[data-testid="${t}"]`;
  const caixa = async (sel) => page.evaluate((s) => { const b = document.querySelector(s).getBoundingClientRect(); return { x: b.x, y: b.y, w: b.width, h: b.height }; }, sel);

  await shot("01a");
  // 02 sala + parede
  const svg = await caixa(T("estudio-planta"));
  await page.click(T("estudio-ferramenta-sala"));
  await page.mouse.click(svg.x + 60, svg.y + 40);
  await page.mouse.move(svg.x + 150, svg.y + 110); await page.mouse.move(svg.x + 200, svg.y + 150);
  await shot("02a");
  await page.mouse.click(svg.x + 200, svg.y + 150);
  await page.waitForTimeout(800);
  await shot("02b");
  await page.click(T("estudio-ferramenta-parede"));
  await page.mouse.click(svg.x + 60, svg.y + 230);
  await page.mouse.move(svg.x + 160, svg.y + 231);
  await page.keyboard.type("3,25");
  await shot("02c");
  await page.keyboard.press("Enter"); await page.keyboard.press("Escape");
  await page.waitForTimeout(500);
  for (let i = 0; i < 2; i += 1) { await page.getByRole("button", { name: "Anular" }).click(); await page.waitForTimeout(250); }
  // 03 vãos: janela nova na parede direita + painel do vão
  const pd = await page.evaluate(() => { const b = document.querySelector('line[data-parede="p0_direita"]').getBoundingClientRect(); return { x: b.x + b.width / 2, y: b.y + b.height * 0.35 }; });
  await page.click(T("estudio-ferramenta-janela"));
  await page.mouse.click(pd.x, pd.y);
  await page.waitForSelector(T("estudio-vao-modelo"));
  await page.selectOption(T("estudio-vao-modelo"), "correr_2").catch(() => {});
  await page.selectOption(T("estudio-vao-protecao"), "estore_termico").catch(() => {});
  await page.click(T("estudio-ferramenta-selecionar"));
  await shot("03a");
  // 04 mobiliário, cota, nota
  const sala = await caixa('polygon[data-divisao^="Sala"]');
  await page.click(T("estudio-ferramenta-objeto"));
  await page.click('[data-objeto-tipo="sofa_3"]'); await page.mouse.click(sala.x + sala.w * 0.22, sala.y + sala.h * 0.3);
  await page.click('[data-objeto-tipo="mesa_centro"]'); await page.mouse.click(sala.x + sala.w * 0.22, sala.y + sala.h * 0.62);
  await page.click('[data-objeto-tipo="mesa_6"]'); await page.mouse.click(sala.x + sala.w * 0.68, sala.y + sala.h * 0.45);
  await page.mouse.move(sala.x + sala.w * 0.5, sala.y + sala.h * 0.8);
  await shot("04a");
  const coz = await caixa('polygon[data-divisao^="Cozinha"]');
  await page.click('[data-objeto-tipo="coz_ilha"]').catch(() => {}); await page.mouse.click(coz.x + coz.w * 0.5, coz.y + coz.h * 0.5);
  await page.click(T("estudio-ferramenta-cota"));
  await page.mouse.click(sala.x + 4, sala.y + sala.h * 0.9);
  await page.mouse.click(sala.x + sala.w - 4, sala.y + sala.h * 0.9);
  await page.click(T("estudio-ferramenta-nota"));
  await page.mouse.click(sala.x + sala.w * 0.5, sala.y + sala.h * 0.12);
  await page.waitForTimeout(600);
  await shot("04b");
  // 05 materiais: divisão e parede
  await page.click(T("estudio-ferramenta-selecionar"));
  await page.mouse.click(sala.x + sala.w * 0.45, sala.y + sala.h * 0.46);
  await page.waitForSelector(T("estudio-divisao"));
  await page.selectOption(T("estudio-divisao-pavimento"), "soalho_carvalho");
  await page.waitForTimeout(900);
  await shot("05a");
  const pf = await page.evaluate(() => { const b = document.querySelector('line[data-parede="p0_tardoz"]').getBoundingClientRect(); return { x: b.x + b.width * 0.5, y: b.y + b.height / 2 }; });
  await page.mouse.click(pf.x + 40, pf.y);
  await page.waitForSelector(T("estudio-parede-fachada"));
  await shot("05b");
  // acabamentos da casa: fachada em granito para o 3D
  await page.mouse.click(svg.x + svg.w - 30, svg.y + svg.h - 40);
  await page.waitForSelector(T("estudio-acabamento-fachada"));
  const idPedra = await page.evaluate(() => { const o = [...document.querySelectorAll('[data-testid="estudio-acabamento-fachada"] option')].find((x) => /granito/i.test(x.textContent)); return o && o.value; });
  if (idPedra) await page.selectOption(T("estudio-acabamento-fachada"), idPedra);
  await page.waitForTimeout(1200);
  // 06 3D
  await verAbas();
  await page.waitForTimeout(1500);
  await shot("06a");
  await page.locator(T("estudio-3d-hora")).fill("9"); await page.selectOption(T("estudio-3d-mes"), "11");
  await shot("06b");
  await page.locator(T("estudio-3d-hora")).fill("16"); await page.selectOption(T("estudio-3d-mes"), "5");
  await page.click('[data-vista="frente"]');
  await shot("06c");
  await page.click('[data-vista="topo"]');
  await shot("06d");
  // 07 visita
  await page.click(T("estudio-3d-visita"));
  await page.waitForTimeout(700);
  await shot("07a");
  for (let i = 0; i < 6; i += 1) await page.click('[data-andar="frente"]');
  const c3 = await caixa(T("estudio-3d"));
  await page.mouse.move(c3.x + 700, c3.y + 200); await page.mouse.down(); await page.mouse.move(c3.x + 420, c3.y + 215, { steps: 6 }); await page.mouse.up();
  await shot("07b");
  await page.click(T("estudio-3d-visita"));
  // 08 alçados e cortes
  await page.click(T("estudio-aba-alcados")); await page.waitForSelector(T("estudio-desenho")); await page.waitForTimeout(1500);
  await shot("08a");
  await page.click(T("estudio-aba-cortes")); await page.waitForTimeout(2000);
  await shot("08b");
  // guardar → medições e processo
  await topo(); await page.click(T("estudio-guardar")); await page.waitForTimeout(1800);
  await verAbas();
  await page.click(T("estudio-aba-medicoes")); await page.waitForTimeout(700);
  await shot("09a");
  await page.evaluate(() => { const e = document.querySelector('[data-testid="estudio-mapa-vaos"]'); window.scrollTo(0, e.getBoundingClientRect().top + window.scrollY - 60); });
  await shot("09b");
  await verAbas();
  await page.click(T("estudio-aba-processo")); await page.waitForTimeout(1800);
  await shot("10a");
  await page.click(T("estudio-aba-3d")); await page.waitForTimeout(1500);
  await page.locator(T("estudio-3d-hora")).fill("17");
  await shot("11a");
  console.log(JSON.stringify({ erros }));
  await browser.close();
})();
