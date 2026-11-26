import { programaSimples, areaMinima } from "../programaSimples";

const O = { quartos: 3, pisos: 2, area: 180, garagem: 2, cobertura: "plana", estilo: "moderno",
  suite: true, escritorio: true, lavandaria: true, piscina: true, jardim: true, terraco: true };

test("gera um programa detalhado por piso que o motor lê à letra", () => {
  const t = programaSimples(O, "pt");
  expect(t).toMatch(/Rés do chão — \d+ m²/);
  expect(t).toMatch(/Primeiro andar — \d+ m²/);
  expect(t).toContain("* Suite:");
  expect(t).toContain("* Quarto 2:");
  expect(t).toContain("Garagem para dois automóveis");
  expect(t).toContain("Piscina exterior de 8 × 4 m");
  expect(t).toContain("Cobertura plana");
});

test("a soma das linhas de cada piso dá o total do piso", () => {
  const t = programaSimples({ ...O, pisos: 1, quartos: 2 }, "fr");
  const [cab, ...linhas] = t.split("\n").filter((l) => l.startsWith("Rez") || l.startsWith("* ") && l.includes("m²"));
  const total = Number(cab.match(/— (\d+)/)[1]);
  const soma = linhas.reduce((s, l) => s + Number(l.match(/: ([\d,]+) m²/)[1].replace(",", ".")), 0);
  expect(Math.abs(soma - total)).toBeLessThanOrEqual(0.5);
});

test("área mínima realista cresce com o programa", () => {
  expect(areaMinima({ ...O, quartos: 5 })).toBeGreaterThan(areaMinima({ ...O, quartos: 2 }));
  expect(areaMinima({ ...O, pisos: 1, quartos: 2, escritorio: false })).toBeLessThan(140);
});
