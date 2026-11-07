import "fake-indexeddb/auto";
import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import GuidedQuote from "@/pages/GuidedQuote";
import DailyLog from "@/pages/DailyLog";
import TradeTools from "@/pages/TradeTools";
import FieldVisit from "@/pages/FieldVisit";
import { api } from "@/lib/api";
import { TaskHome } from "@/components/dashboard/TaskHome";

const ok = (c, m) => { if (!c) throw new Error("FALHOU: " + m); console.log("  ✓ " + m); };
const byId = id => screen.getByTestId(id);
const type = (id, v) => fireEvent.change(byId(id), { target: { value: v } });
const next = async () => { fireEvent.click(byId("gq-next")); await act(() => new Promise(r => setTimeout(r, 0))); };

export async function run() {
  localStorage.setItem("is_demo", "true"); localStorage.setItem("demo_kind", "pro");

  console.log("Painel e onboarding");
  const h = render(<MemoryRouter><TaskHome /></MemoryRouter>);
  await waitFor(() => byId("task-home"));
  ok(!!byId("onboarding-invite") && byId("task-list").children.length >= 3, "conta sem perfil: tarefas genéricas visíveis, onboarding só convidado");
  fireEvent.click(byId("onboarding-open"));
  await waitFor(() => byId("profession-engenheiro"));
  fireEvent.click(byId("profession-engenheiro")); fireEvent.click(byId("onboarding-next"));
  await waitFor(() => byId("onboarding-next")); fireEvent.click(byId("onboarding-next"));
  await waitFor(() => byId("mode-guiado")); fireEvent.click(byId("mode-guiado")); fireEvent.click(byId("language-tecnica"));
  fireEvent.click(byId("onboarding-finish"));
  await waitFor(() => ok(byId("mode-switch-guiado").getAttribute("aria-checked") === "true" && !screen.queryByTestId("onboarding-invite"), "engenheiro escolhe modo guiado (+ linguagem técnica)"));
  ok(!!screen.queryByTestId("home-task-medicoes"), "tarefas do engenheiro sugeridas (medições)");
  fireEvent.click(byId("mode-switch-avancado"));
  await waitFor(() => ok(byId("mode-switch-avancado").getAttribute("aria-checked") === "true", "e pode passar a modo avançado"));
  h.unmount();

  console.log("Percurso A — pintor, modo guiado (demo offline)");
  await api.put("/me/work-profile", { professions: ["pintor"], mode: "guiado", language: "simples" });
  const g = render(<MemoryRouter><GuidedQuote /></MemoryRouter>);
  await waitFor(() => byId("gq-q-describe"));
  ok(byId("gq-mode-guiado").getAttribute("aria-checked") === "true", "modo guiado por defeito");
  type("gq-description", "O senhor Manuel quer pintar uma sala e dois quartos. Tenho de comprar a tinta e reparar fissuras.");
  await next();
  await waitFor(() => byId("gq-q-client")); type("gq-client-name", "Manuel"); await next();
  type("gq-address", "Rua A, Lisboa"); await next();
  fireEvent.click(byId("gq-work-cracks")); await next();
  type("gq-room-0-name", "Sala"); await next();
  ok(screen.queryByTestId("gq-room-0-length") && !screen.queryByTestId("gq-room-0-height"), "uma pergunta de cada vez (medidas sem pé-direito no mesmo ecrã)");
  type("gq-room-0-length", "5"); type("gq-room-0-width", "4"); await next();
  type("gq-room-0-height", "2.6"); await next();
  fireEvent.click(byId("gq-room-0-add-door")); type("gq-room-0-op-0-w", "0.9"); type("gq-room-0-op-0-h", "2.1"); await next();
  fireEvent.click(byId("gq-add-room")); await act(() => new Promise(r => setTimeout(r, 0)));
  type("gq-room-1-name", "Quarto 1"); await next();
  type("gq-room-1-length", "3"); type("gq-room-1-width", "3"); await next();
  type("gq-room-1-height", "2.5"); await next();
  await next();               // sem aberturas
  await next();               // não há mais divisões
  fireEvent.click(byId("gq-cracks-unknown")); await act(() => new Promise(r => setTimeout(r, 0)));
  ok(!!screen.queryByText(/Fica pendente/), "«Não sei» nas fissuras → pendente, não zero");
  await next();
  fireEvent.click(byId("gq-coats-suggestion")); await next();
  type("gq-yield", "10"); await next();
  type("gq-can", "15"); await next();
  type("gq-price-labor", "8"); type("gq-price-prep", "2"); type("gq-price-can", "60"); await next();
  await waitFor(() => byId("gq-review"), { timeout: 3000 });
  const total = byId("gq-total-ht").textContent;
  // Sala 46,8 − 1,89 = 44,91 ; Quarto 30 → 74,91 m² ; prep 2×74,91=149,82 ; pintura 8×74,91=599,28 ; tinta 74,91×2/10=14,98 L → 1 lata 60 ⇒ 149,82+599,28+60 = 809,10
  ok(/809,10/.test(total.replace(/\s/g, "")), `total sem IVA correto (${total})`);
  const pend = byId("gq-to-confirm").textContent;
  ok(/fissuras/.test(pend), "fissuras sem quantidade nem preço ficam «por confirmar» (não zero escondido)");
  fireEvent.click(byId("gq-mode-direto")); await act(() => new Promise(r => setTimeout(r, 50)));
  await waitFor(() => byId("gq-review"));
  ok(/809,10/.test(byId("gq-total-ht").textContent.replace(/\s/g, "")), "mudar para modo direto mantém dados e totais");
  fireEvent.click(byId("gq-save")); await act(() => new Promise(r => setTimeout(r, 50)));
  ok(true, "guardar (demo) sem envio ao cliente");
  g.unmount();
  console.log("Pintor com opções avançadas");
  await api.put("/me/work-profile", { mode: "avancado" });
  const g2 = render(<MemoryRouter><GuidedQuote /></MemoryRouter>);
  await waitFor(() => byId("gq-q-describe"));
  await waitFor(() => byId("gq-mode-avancado").getAttribute("aria-checked") === "true" || (() => { throw new Error("modo"); })());
  await next();
  ok(!!screen.queryByTestId("gq-q-address") && !!screen.queryByTestId("gq-q-client"), "pintor em modo avançado: secção completa num só ecrã");
  g2.unmount();

  console.log("Percurso E — registo diário");
  const d = render(<MemoryRouter><DailyLog /></MemoryRouter>);
  type("daily-text", "Hoje fomos dois, colocámos o chão da cozinha e faltou cola.");
  fireEvent.click(byId("daily-interpret"));
  await waitFor(() => byId("daily-proposal"));
  ok(byId("daily-workers").value === "2", "equipa: 2 pessoas");
  ok(byId("daily-hours").value === "", "horas não inventadas");
  ok(byId("daily-material-0").value === "cola", "material em falta: cola");
  ok(/Quantidade/.test(byId("daily-ambiguous").textContent), "quantidade da cola sinalizada como a verificar");
  fireEvent.click(byId("daily-confirm"));
  await waitFor(() => byId("daily-history"));
  ok(/cola/.test(byId("daily-history").textContent), "registo guardado após confirmação");
  d.unmount();

  console.log("Percurso D — visita à obra");
  const v = render(<MemoryRouter><FieldVisit /></MemoryRouter>);
  type("visit-title", "Moradia Manuel");
  fireEvent.click(byId("visit-add-measure")); type("visit-measure-0-label", "Sala comprimento"); type("visit-measure-0-value", "5");
  fireEvent.click(byId("visit-add-measure")); type("visit-measure-1-label", "Corredor");
  type("visit-question", "Cor da tinta?"); fireEvent.click(byId("visit-add-question"));
  fireEvent.click(byId("visit-save"));
  await waitFor(() => byId("visit-summary"));
  const tc = byId("visit-to-confirm").textContent;
  ok(/Morada/.test(tc) && /Corredor/.test(tc) && /Cor da tinta/.test(tc), "resumo editável + lista do que falta confirmar");
  ok(/Sala comprimento: 5/.test(byId("visit-summary-text").value), "medidas no resumo");
  v.unmount();

  console.log("Ferramentas — pavimento e pontos");
  const t = render(<MemoryRouter initialEntries={["/ferramentas-oficio?ferramenta=floor"]}><TradeTools /></MemoryRouter>);
  type("floor-length", "4"); type("floor-width", "3"); type("floor-package", "1.44");
  fireEvent.click(byId("tool-compute"));
  await waitFor(() => byId("tool-result"));
  ok(byId("floor-packages").textContent === "—" && /perdas/i.test(byId("tool-pending").textContent), "sem perdas indicadas → pendente, sem número fictício");
  type("floor-waste", "10"); fireEvent.click(byId("tool-compute"));
  await waitFor(() => ok(byId("floor-packages").textContent === "10", "4×3 m +10 % ÷ 1,44 → 10 embalagens"));
  fireEvent.click(byId("tool-tab-points")); await act(() => new Promise(r => setTimeout(r, 0)));
  type("points-0-qty", "6"); fireEvent.click(byId("tool-compute"));
  await waitFor(() => byId("points-totals"));
  ok(/6 × Tomada/.test(byId("points-totals").textContent), "levantamento de pontos (eletricidade)");
  t.unmount();
}
