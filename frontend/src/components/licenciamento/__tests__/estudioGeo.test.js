import * as G from "@/components/licenciamento/estudioGeo";

const tipos = { ext_30: { camadas: [{ esp_m: 0.015 }, { esp_m: 0.22 }, { esp_m: 0.06 }, { esp_m: 0.005 }] } };
const base = () => ({
  pisos: [{ id: "p0", nome: "Rés-do-chão", pe_direito_m: 2.7, laje_m: 0.25 }], tipos_parede: tipos, rotulos: [],
  paredes: [{ id: "w1", piso: "p0", a: [0, 0], b: [10, 0], tipo: "ext_30" }, { id: "w2", piso: "p0", a: [10, 0], b: [10, 8], tipo: "ext_30" }],
  vaos: [{ id: "v1", parede: "w1", tipo: "janela", pos_m: 5, largura_m: 1.2, altura_m: 1.2, peitoril_m: 0.9 }],
});

test("espessura = soma das camadas", () => {
  expect(G.espessuraTipo(tipos.ext_30)).toBeCloseTo(0.30, 6);
});

test("o cursor cola às pontas, fica ortogonal e respeita a grelha de 5 cm", () => {
  const m = base();
  expect(G.encaixar([9.85, 0.2], m.paredes).ponto).toEqual([10, 0]);
  expect(G.encaixar([3.02, 4.31], m.paredes, [3, 2]).ponto).toEqual([3, 4.3]);          // quase vertical → vertical
  expect(G.encaixar([4.123, 5.678], m.paredes).ponto).toEqual([4.1, 5.7]);
  expect(G.encaixar([5.02, 0.15], m.paredes, [5, 4]).ponto).toEqual([5, 0]);            // ortogonal até ao eixo da parede
});

test("um vão novo é colocado onde cabe, sem pisar os existentes nem sair da parede", () => {
  const m = base();
  const w1 = m.paredes[0];
  expect(G.posicaoVao(m, w1, 0.1, 0.9)).toBeCloseTo(0.5, 6);                             // 5 cm de folga à ponta
  const p = G.posicaoVao(m, w1, 5, 0.9);                                                 // em cima da janela existente
  expect(Math.abs(p - 5)).toBeGreaterThanOrEqual((1.2 + 0.9) / 2 + 0.02 - 1e-9);
  expect(G.posicaoVao(m, { id: "x", a: [0, 0], b: [0.8, 0] }, 0.4, 0.9)).toBeNull();     // parede demasiado curta
  const r = G.adicionarVao(m, w1, 8, "porta", { largura_m: 0.9, altura_m: 2.1, peitoril_m: 0 });
  expect(r.modelo.vaos).toHaveLength(2);
  expect(r.modelo.vaos[1]).toMatchObject({ parede: "w1", tipo: "porta", pos_m: 8 });
});

test("apagar uma parede apaga os seus vãos; mudar o comprimento mantém o ponto a e a direção", () => {
  const m = base();
  expect(G.removerParede(m, "w1").vaos).toHaveLength(0);
  const m2 = G.comprimentoParede(m, "w2", 6);
  expect(m2.paredes[1].a).toEqual([10, 0]);
  expect(m2.paredes[1].b).toEqual([10, 6]);
  expect(G.adicionarParede(m, "p0", [0, 0], [0.05, 0], "ext_30")).toBe(m);               // menos de 10 cm: ignorada
});

test("novo piso copia as paredes e as janelas do piso de baixo; remover o piso leva tudo o que é dele", () => {
  const m = G.adicionarPiso(base());
  expect(m.pisos).toHaveLength(2);
  expect(m.paredes.filter((w) => w.piso === m.pisos[1].id)).toHaveLength(2);
  expect(m.vaos.filter((v) => v.id.startsWith(m.pisos[1].id))).toHaveLength(1);
  expect(new Set(m.paredes.map((w) => w.id)).size).toBe(m.paredes.length);
  const v = G.removerUltimoPiso(m);
  expect(v.pisos).toHaveLength(1);
  expect(v.paredes).toHaveLength(2);
  expect(v.vaos).toHaveLength(1);
});

test("acabamentos e nome por divisão ficam no rótulo que está dentro dela", () => {
  const sala = { nome: "Divisão 1", centro: [2, 2], pts: [[0, 0], [4, 0], [4, 4], [0, 4]] };
  const outra = { nome: "Divisão 2", centro: [6, 2], pts: [[4, 0], [8, 0], [8, 4], [4, 4]] };
  expect(G.dentroPoligono([2, 2], sala.pts)).toBe(true);
  expect(G.dentroPoligono([5, 2], sala.pts)).toBe(false);
  let m = G.definirDivisao(base(), "p0", sala, { pavimento: "soalho_carvalho" });
  expect(m.rotulos).toEqual([{ piso: "p0", x: 2, y: 2, nome: "Divisão 1", pavimento: "soalho_carvalho" }]);
  m = G.definirDivisao(m, "p0", sala, { nome: "Sala", teto: "teto_madeira" });
  m = G.definirDivisao(m, "p0", outra, { pavimento: "gres_cinza" });
  expect(m.rotulos).toHaveLength(2);                                   // um rótulo por divisão, nunca duplicado
  expect(m.rotulos[0]).toMatchObject({ nome: "Sala", pavimento: "soalho_carvalho", teto: "teto_madeira" });
  m = G.definirDivisao(m, "p0", sala, { pavimento: "", nome: "  " });  // vazio = voltar ao da casa; nome vazio é ignorado
  expect(m.rotulos[0].pavimento).toBeUndefined();
  expect(m.rotulos[0].nome).toBe("Sala");
  expect(G.rotuloDaDivisao(m, "p1", sala.pts)).toBe(-1);               // outro piso não conta
});

test("escadas: colocar na grelha, rodar, remover; remover o último piso leva as escadas que subiam para ele", () => {
  let m = G.adicionarPiso(base());
  const r = G.adicionarEscada(m, "p0", [3.02, 4.98]);
  expect(r.modelo.escadas[0]).toMatchObject({ id: "e1", piso: "p0", tipo: "u", x: 3, y: 5, rot: 0, largura_m: 0.9, cobertor_m: 0.25 });
  m = G.mudarEscada(r.modelo, "e1", { rot: 90, tipo: "l" });
  expect(m.escadas[0]).toMatchObject({ rot: 90, tipo: "l" });
  expect(G.removerUltimoPiso(m).escadas).toHaveLength(0);              // sem piso acima, a escada deixa de fazer sentido
  expect(G.removerEscada(m, "e1").escadas).toHaveLength(0);
});

test("sala retangular cria quatro paredes fechadas", () => {
  const m = G.adicionarSala({ ...base(), paredes: [] }, "p0", [5, 6], [1, 2], "ext_30");
  expect(m.paredes).toHaveLength(4);
  expect(m.paredes[0].a).toEqual([1, 2]);
  expect(m.paredes[3].b).toEqual([1, 2]);
  expect(G.adicionarSala(base(), "p0", [0, 0], [0.3, 4], "ext_30").paredes).toHaveLength(2);       // demasiado estreita
});

test("mover uma parede leva as pontas das paredes que nela tocam", () => {
  const m = G.moverParede(base(), "w2", 2, 0);
  expect(m.paredes[1].a).toEqual([12, 0]);
  expect(m.paredes[1].b).toEqual([12, 8]);
  expect(m.paredes[0].b).toEqual([12, 0]);          // a parede w1 esticou
  expect(m.paredes[0].a).toEqual([0, 0]);
  // encontro em T: a parede interior que acaba no eixo da parede movida acompanha-a
  const t = { ...base(), paredes: [...base().paredes, { id: "i", piso: "p0", a: [4, 5], b: [10, 5], tipo: "ext_30" }, { id: "longe", piso: "p0", a: [4, 5], b: [4, 0], tipo: "ext_30" }] };
  const mt = G.moverParede(t, "w2", 1.5, 0);
  expect(mt.paredes.find((w) => w.id === "i").b).toEqual([11.5, 5]);
  expect(mt.paredes.find((w) => w.id === "longe")).toEqual(t.paredes[3]);
});

test("objetos: contorno rodado, cotas e notas", () => {
  const sofa = { largura_m: 2.2, prof_m: 0.95, forma: "ret" };
  const c = G.contornoObjeto({ x: 5, y: 5, rot: 90 }, sofa);
  const xs = c.pts.map((p) => p[0]), ys = c.pts.map((p) => p[1]);
  expect(Math.max(...xs) - Math.min(...xs)).toBeCloseTo(0.95, 6);
  expect(Math.max(...ys) - Math.min(...ys)).toBeCloseTo(2.2, 6);
  let r = G.adicionarObjeto(base(), "p0", "sofa_3", [2.02, 3.04]);
  expect(r.modelo.objetos[0]).toMatchObject({ id: "o1", x: 2, y: 3.05, tipo: "sofa_3" });
  expect(G.removerObjeto(G.mudarObjeto(r.modelo, "o1", { rot: 45 }), "o1").objetos).toHaveLength(0);
  r = G.adicionarCota(base(), "p0", [0, 0], [4, 0]);
  const g = G.geoCota(r.modelo.cotas[0]);
  expect(g.L).toBeCloseTo(4, 6);
  expect(g.p).toEqual([0, 0.6]);
  expect(G.adicionarNota(base(), "p0", [1, 1], "   ").id).toBeNull();
  expect(G.adicionarNota(base(), "p0", [1, 1], " Pavimento radiante ").modelo.notas[0].texto).toBe("Pavimento radiante");
  expect(G.removerUltimoPiso({ ...base(), pisos: [...base().pisos, { id: "p1" }], objetos: [{ id: "o1", piso: "p1" }] }).objetos).toHaveLength(0);
});

test("sol: meio-dia solar a sul, altura = 90 − latitude + declinação", () => {
  const verao = G.sol(40, 172, 12), inverno = G.sol(40, 355, 12);
  expect(verao.azimute).toBeCloseTo(180, 3);
  expect(verao.altura).toBeCloseTo(90 - 40 + 23.45, 1);
  expect(inverno.altura).toBeCloseTo(90 - 40 - 23.45, 1);
  expect(G.sol(40, 80, 8).azimute).toBeLessThan(180);            // de manhã o sol está a nascente
  // frente virada a sul: ao meio-dia o sol está à frente da casa (−y) e por cima
  const v = G.vetorSol(verao.altura, verao.azimute, 180);
  expect(v[0]).toBeCloseTo(0, 6); expect(v[1]).toBeLessThan(0); expect(v[2]).toBeGreaterThan(0.9);
  // de manhã, com a frente a sul, o sol está à direita (nascente = +x)
  const m = G.sol(40, 80, 8); expect(G.vetorSol(m.altura, m.azimute, 180)[0]).toBeGreaterThan(0);
});
