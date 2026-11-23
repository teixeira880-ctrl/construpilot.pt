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
