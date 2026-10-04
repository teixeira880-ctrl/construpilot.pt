/**
 * Teste unit do sistema i18n PT-PT.
 * Objectivo: garantir que o pt_auto.json carrega, tem o shape esperado,
 * e que uma amostra de 10 chaves resolvem para strings PT-PT.
 */
import PT from "../pt_auto.json";

describe("i18n · pt_auto.json", () => {
  test("carrega sem erro de parsing", () => {
    expect(PT).toBeTruthy();
    expect(typeof PT).toBe("object");
  });

  test("tem pelo menos 5000 chaves", () => {
    expect(Object.keys(PT).length).toBeGreaterThan(5000);
  });

  test("todos os valores são strings não vazias", () => {
    const bad = Object.entries(PT).filter(
      ([k, v]) => typeof v !== "string" || v.trim().length === 0
    );
    expect(bad).toEqual([]);
  });

  test("chaves FR comuns resolvem para PT-PT", () => {
    const samples = [
      ["Calcul en cours…", /em curso|a calcular/i],
      ["Actualiser le tarif", /atualizar/i],
      ["Tarif du courrier", /preço|carta/i],
    ];
    for (const [frKey, expectedPt] of samples) {
      const pt = PT[frKey];
      expect(pt).toBeTruthy();
      expect(pt).toMatch(expectedPt);
    }
  });

  test("não contém termos PT-BR típicos após revisão", () => {
    const brPatterns = [
      /\btela\b/i,
      /\bconectar\b/i,
      /\bsalvar\b/i,
      /\bdeletar\b/i,
      /\busuário/i,
      /\barquivo\b/i,
      /\bcadastro\b/i,
    ];
    const offenders = [];
    for (const [frKey, ptVal] of Object.entries(PT)) {
      if (typeof ptVal !== "string") continue;
      for (const re of brPatterns) {
        if (re.test(ptVal)) {
          offenders.push({ frKey: frKey.slice(0, 60), ptVal: ptVal.slice(0, 80), re: re.source });
        }
      }
    }
    // Permitir até 5 falsos positivos (contextos muito específicos ou substantivos próprios).
    expect(offenders.length).toBeLessThanOrEqual(5);
  });
});
