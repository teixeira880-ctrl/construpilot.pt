// Paridade das regras offline (engine.js) com o servidor (recommend.py): mesmos casos que o pytest.
import cases from "../cases.json";
import { recommendClient, recommendPartner, deepQuestionsFor, CAPS, PUBLIC_STATUSES, catalog } from "../engine";
import { buildSteps, cleanForServer } from "../../pages/connect/ConnectClient";

describe("Discovery Engine — paridade offline", () => {
  test.each(cases.cases.map((c) => [c.name, c]))("%s", (_name, c) => {
    const r = recommendClient(c.answers);
    const e = c.expect;
    expect(r.primary_case).toBe(e.primary_case);
    expect(r.demo).toBe(e.demo);
    expect(r.track).toBe(e.track);
    expect(r.capabilities.map((x) => x.id)).toEqual(e.capabilities);
    expect(r.process.current).toBe(e.process_current);
    expect(r.process.with).toBe(e.process_with);
    expect(r.value_defaults.quotes_per_month).toBe(e.quotes_per_month);
    expect(r.value_defaults.hours_per_quote).toBe(e.hours_per_quote);
    if ("needs_human_review" in e) expect(r.needs_human_review).toBe(e.needs_human_review);
  });

  test("nunca recomenda capacidades não públicas", () => {
    for (const p of catalog.pains) {
      const r = recommendClient({ activity: "construction_company", pains: [p.id] });
      r.capabilities.forEach((c) => expect(PUBLIC_STATUSES).toContain(CAPS[c.id].status));
    }
  });

  test("parceiro: caso de utilização por tipo", () => {
    expect(recommendPartner({ partner_type: "design_office" }).use_case).toBe("cap_takeoff");
  });
});

describe("Discovery Engine — percurso adaptativo", () => {
  test("modo rápido apresenta entre 5 e 7 perguntas", () => {
    for (const c of cases.cases) {
      const n = buildSteps(c.answers, "quick").length;
      expect(n).toBeGreaterThanOrEqual(5);
      expect(n).toBeLessThanOrEqual(7);
    }
  });
  test("pintor recebe pergunta de superfícies; engenheiro não", () => {
    const painter = deepQuestionsFor({ activity: "painting", pains: ["p_quote_slow"] }, "quick").map((q) => q.id);
    const eng = deepQuestionsFor({ activity: "civil_engineer", pains: ["p_quote_slow"] }, "quick").map((q) => q.id);
    expect(painter).toContain("t_surfaces");
    expect(eng).not.toContain("t_surfaces");
  });
  test("stand: problema + 3 perguntas", () => {
    expect(buildSteps({ activity: "general_contractor" }, "stand").map((s) => s.id)).toEqual(["pains", "activity", "volume", "urgency"]);
  });
  test("cleanForServer remove respostas que deixaram de se aplicar", () => {
    const out = cleanForServer({ activity: "architect", volume: { quotes_per_month: "q6_15", projects_parallel: "p3_5" },
      pains: ["p_measure"], other_text: "x", deep: { b_time: "h1_3", a_formats: ["pdf"] } }, "quick");
    expect(out.volume).toEqual({ projects_parallel: "p3_5" });
    expect(out.other_text).toBe("");
    expect(out.deep).toEqual({ a_formats: ["pdf"] });
  });
});
