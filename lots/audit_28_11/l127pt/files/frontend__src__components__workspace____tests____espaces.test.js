import { WORKSPACE_LINKS, workspaceEssentials } from "../navigation";
import { APP_FAMILIES as APP_SUITES } from "../families";
import { SPACES, spaceOf, METIER_ESSENTIALS, METIERS } from "../espaces";

describe("espaces par objectif (ergonomie phase 2)", () => {
  it("chaque suite métier tombe dans un des 5 espaces", () => {
    const sansEspace = APP_SUITES.filter(s => s.id !== "api")
      .map(s => WORKSPACE_LINKS.find(l => l.hub === s.id))
      .filter(l => l && spaceOf(l) === "outros");
    expect(sansEspace.map(l => l.to)).toEqual([]);
  });
  it("5 espaces, ids uniques", () => {
    expect(SPACES).toHaveLength(5);
    expect(new Set(SPACES.map(s => s.id)).size).toBe(5);
  });
});

describe("menu par métier (ergonomie phase 3)", () => {
  const links = WORKSPACE_LINKS.filter(l => !l.locked);
  it("chaque route épinglée par métier existe dans le catalogue", () => {
    for (const paths of Object.values(METIER_ESSENTIALS)) {
      for (const p of paths) expect(WORKSPACE_LINKS.some(l => l.to === p)).toBe(true);
    }
  });
  it("chaque métier a un libellé et un menu", () => {
    for (const m of METIERS.filter(x => x.id)) expect(METIER_ESSENTIALS[m.id]).toBeTruthy();
  });
  it("sans métier, le menu pro générique est inchangé", () => {
    expect(workspaceEssentials(links, true, "").map(l => l.to)).toEqual(workspaceEssentials(links, true).map(l => l.to));
  });
  it("un particulier garde son menu même avec un métier mémorisé", () => {
    expect(workspaceEssentials(links, false, "architecte").map(l => l.to)).toEqual(workspaceEssentials(links, false).map(l => l.to));
  });
  it("architecte : l'atelier BIM est épinglé", () => {
    expect(workspaceEssentials(links, true, "architecte").map(l => l.to)).toContain("/arquiteto-bim");
  });
});
