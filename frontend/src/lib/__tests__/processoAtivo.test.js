import { comProcesso, paramsDoTrabalho, processoAtivo, definirProcessoAtivo, limparProcessoAtivo } from "../processoAtivo";

test("comProcesso junta o processo sem perder parâmetros nem âncora", () => {
  expect(comProcesso("/atelier-arquiteto?projet=arch_1#x", "cht_9")).toBe("/atelier-arquiteto?projet=arch_1&chantier=cht_9#x");
  expect(comProcesso("/bim", "cht_9")).toBe("/bim?chantier=cht_9");
  expect(comProcesso("/plan?chantier=old", "cht_9")).toBe("/plan?chantier=cht_9");
  expect(comProcesso("https://externo.com", "cht_9")).toBe("https://externo.com");
});

test("paramsDoTrabalho ignora navegação e guarda o identificador do trabalho", () => {
  expect(paramsDoTrabalho("?projet=arch_516faad6faec&chantier=c1&tab=x&utm_source=y")).toEqual({ projet: "arch_516faad6faec" });
  expect(paramsDoTrabalho("")).toEqual({});
});

test("processo ativo é por conta", () => {
  definirProcessoAtivo("u1", "cht_1", "Moradia");
  expect(processoAtivo("u1")).toMatchObject({ chantierId: "cht_1", nome: "Moradia" });
  expect(processoAtivo("u2")).toBeNull();
  limparProcessoAtivo();
  expect(processoAtivo("u1")).toBeNull();
});
