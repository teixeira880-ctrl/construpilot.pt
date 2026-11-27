import { promptDoModelo } from "../promptRender";

test("o pedido do render vem dos materiais e exteriores do modelo", () => {
  const p = promptDoModelo({ pisos: [{}, {}], medicoes: {
    acabamentos: [{ elemento: "Fachada exterior", material: "Reboco branco" }, { elemento: "Cobertura", material: "Laje plana" },
      { elemento: "Caixilharia (vãos exteriores)", material: "Alumínio antracite" }],
    exteriores: [{ nome: "Piscina retangular (plano de água)" }, { nome: "Relvado" }] } });
  expect(p).toContain("Facade finish: Reboco branco");
  expect(p).toContain("Roof: Laje plana");
  expect(p).toContain("Window frames: Alumínio antracite");
  expect(p).toContain("Piscina retangular");
  expect(p).toContain("2-storey");
  expect(p.length).toBeLessThanOrEqual(990);
});

test("telhado plano nunca pede telhas, telhado inclinado nunca fica plano", () => {
  const plano = promptDoModelo({ cobertura: { tipo: "plana" }, medicoes: { acabamentos: [{ elemento: "Cobertura", material: "Cobertura plana com proteção em seixo" }] } });
  expect(plano).toContain("FLAT roof");
  expect(plano).toContain("No roof tiles");
  const duas = promptDoModelo({ cobertura: { tipo: "duas_aguas", inclinacao_graus: 35 }, medicoes: { acabamentos: [{ elemento: "Cobertura", material: "Telha lusa" }] } });
  expect(duas).toContain("gable roof");
  expect(duas).toContain("35 degrees");
  expect(duas).toContain("never flat");
});
