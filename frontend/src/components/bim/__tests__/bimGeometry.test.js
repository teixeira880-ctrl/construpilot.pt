import { boundsOf, distance, formatQty, isValidMesh, isVisible, PROFILE_COPY } from "../bimGeometry";

describe("BIM Studio — funções do visualizador", () => {
  test("valida malhas recebidas da API", () => {
    expect(isValidMesh({ p: [0, 0, 0, 1, 0, 0, 0, 1, 0], i: [0, 1, 2], c: [1, 1, 1] })).toBe(true);
    expect(isValidMesh({ p: [0, 0, 0, 1, 0, 0], i: [0, 1, 2] })).toBe(false); // índice fora do intervalo
    expect(isValidMesh({ p: [0, 0], i: [] })).toBe(false);
    expect(isValidMesh(null)).toBe(false);
  });

  test("filtros por piso, categoria, ocultos e isolados", () => {
    const wall = { gid: "w", category: "paredes", storey_gid: "s0" };
    const space = { gid: "e", category: "espacos", storey_gid: "s0" };
    const none = { storeys: new Set(), categories: new Set(), hidden: new Set(), isolated: new Set() };
    expect(isVisible(wall, none)).toBe(true);
    expect(isVisible(space, none)).toBe(false); // espaços escondidos por defeito
    expect(isVisible(space, { ...none, categories: new Set(["espacos"]) })).toBe(true);
    expect(isVisible(wall, { ...none, storeys: new Set(["s1"]) })).toBe(false);
    expect(isVisible(wall, { ...none, hidden: new Set(["w"]) })).toBe(false);
    expect(isVisible(wall, { ...none, isolated: new Set(["x"]) })).toBe(false);
    expect(isVisible(wall, { ...none, isolated: new Set(["w"]), hidden: new Set(["w"]) })).toBe(true);
  });

  test("caixa envolvente, distância e formatação pt-PT", () => {
    const b = boundsOf([[0, 0, 0, 10, 8, 3]]);
    expect(b.size).toBe(10);
    expect(b.center).toEqual([5, 4, 1.5]);
    expect(boundsOf([])).toBeNull();
    expect(distance([0, 0, 0], [3, 4, 0])).toBe(5);
    expect(formatQty(28, "m²")).toMatch(/^28\s?m²$/);
    expect(formatQty(null, "m")).toBe("—");
    expect(formatQty(2, "u")).toBe("2 u");
  });

  test("todos os perfis têm separador inicial e introdução", () => {
    Object.values(PROFILE_COPY).forEach((p) => {
      expect(["modelo", "medicoes", "orcamento", "versoes"]).toContain(p.tab);
      expect(p.intro.length).toBeGreaterThan(20);
    });
  });
});

import { partitionFaces, sideOfNormal, visibleZones, hexToRgb, sideDisplayLabel } from "../bimGeometry";

describe("BIM Studio — revestimentos por face", () => {
  const wallFaces = { kind: "wall", axis: [0, 1], z0: 0, z1: 2.8, sides: { A: { label: "exterior" }, B: { label: "interior" } } };
  test("lado a partir da normal", () => {
    expect(sideOfNormal([0, 1, 0], wallFaces)).toBe("A");
    expect(sideOfNormal([0, -1, 0], wallFaces)).toBe("B");
    expect(sideOfNormal([1, 0, 0], wallFaces)).toBeNull();
    expect(sideOfNormal([0, 0, 1], { kind: "slab" })).toBe("top");
    expect(sideOfNormal([0, 0, -1], { kind: "slab" })).toBe("bottom");
  });
  test("partição dos triângulos por lado preserva todos os triângulos", () => {
    // dois triângulos: um virado para +Y (lado A), outro para -Y (lado B), um para +X (topo/borda)
    const p = [0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1];
    const idx = [0, 1, 2, 3, 4, 5, 6, 7, 8];
    const { index, groups } = partitionFaces(p, idx, wallFaces);
    expect(index.length).toBe(9);
    expect(groups.reduce((s, g) => s + g.count, 0)).toBe(9);
    expect(groups.map((g) => g.side).sort()).toEqual(["A", "B", null].sort());
  });
  test("zonas visíveis e cores", () => {
    const z = visibleZones([{ color: "#FFFFFF", pattern: "azulejo", from_m: 0, to_m: 1.2 }, { color: "#E8D9C0", pattern: "liso", from_m: 1.2 }], wallFaces);
    expect(z).toHaveLength(2);
    expect(z[0].to).toBe(1.2);
    expect(z[1].to).toBeGreaterThan(2.8);
    expect(z[0].pattern).toBe(2);
    expect(hexToRgb("#FF0000")).toEqual([1, 0, 0]);
    expect(sideDisplayLabel(wallFaces, "A", false)).toBe("Exterior (lado A)");
    expect(sideDisplayLabel(wallFaces, "A", true)).toBe("Interior (lado A)");
  });
});
