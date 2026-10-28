import { act } from "react";
import { createRoot } from "react-dom/client";
import { DomTranslator } from "@/components/DomTranslator";

jest.mock("@/context/I18nContext", () => ({ useI18n: () => ({ lang: "pt" }) }));

const flush = async () => {
  for (let i = 0; i < 5; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
  }
};

beforeAll(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  global.requestAnimationFrame = (cb) => setTimeout(cb, 0);
});

// Monta o tradutor fora do <body> traduzido, como na app (componente sem UI).
const render = (el) => {
  const host = document.createElement("div");
  document.documentElement.appendChild(host);
  act(() => { createRoot(host).render(el); });
};

test("traduz o conteúdo inicial depois de carregar o dicionário", async () => {
  document.body.innerHTML = "<p id='a'>Tarif du courrier</p>";
  render(<DomTranslator />);
  await flush();
  expect(document.getElementById("a").textContent).toBe("Preço da carta");
});

test("traduz só os nós adicionados depois, e respeita data-no-translate", async () => {
  document.body.innerHTML = "<div id='root'></div>";
  render(<DomTranslator />);
  await flush();
  const root = document.getElementById("root");
  root.insertAdjacentHTML("beforeend",
    "<span id='b'>Calcul en cours…</span><span data-no-translate><b id='c'>Calcul en cours…</b></span>");
  root.querySelector("#b").setAttribute("title", "Actualiser le tarif");
  await flush();
  expect(document.getElementById("b").textContent).toBe("Cálculo em curso…");
  expect(document.getElementById("b").getAttribute("title")).toBe("Atualizar o preço");
  expect(document.getElementById("c").textContent).toBe("Calcul en cours…");
});

test("traduz texto alterado num nó existente", async () => {
  document.body.innerHTML = "<p id='d'>x</p>";
  render(<DomTranslator />);
  await flush();
  document.getElementById("d").firstChild.nodeValue = "Vérifier le suivi";
  await flush();
  expect(document.getElementById("d").textContent).toBe("Verificar o seguimento");
});
