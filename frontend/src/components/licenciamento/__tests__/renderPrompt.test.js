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
