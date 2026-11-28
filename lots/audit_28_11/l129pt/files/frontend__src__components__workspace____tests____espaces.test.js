import { SPACES, SPACE_ORDER, spaceOf, METIER_ESSENTIALS, METIERS } from "../espaces";

describe("espaços por objetivo (ergonomia fase 2)", () => {
  it("5 espaços, ids únicos, «outros» no fim", () => {
    expect(SPACES).toHaveLength(5);
    expect(new Set(SPACE_ORDER).size).toBe(6);
    expect(SPACE_ORDER.at(-1)).toBe("outros");
  });
  it("cada suite do .pt cai num espaço", () => {
    const hubs = ["estimar", "documentos", "precos", "arquiteto", "licenciamento", "imagens", "engenharia", "plantas", "obra", "faturacao", "empresa", "oportunidades", "diagnostico"];
    for (const h of hubs) expect(spaceOf({ hub: h })).not.toBe("outros");
    expect(spaceOf({ to: "/assistant" })).toBe("outros");
  });
});

describe("menu por profissão (ergonomia fase 3)", () => {
  it("cada profissão tem menu, a começar pelo início", () => {
    for (const m of METIERS.filter(x => x.id)) {
      expect(METIER_ESSENTIALS[m.id].length).toBeGreaterThanOrEqual(5);
      expect(METIER_ESSENTIALS[m.id][0]).toBe("/dashboard");
    }
  });
});
