// AK.3 — Páginas dedicadas por tipo (reutilizam PedidosHub com kind fixo).
import PedidosHub from "./PedidosHub";

export const PedidosContactos = () => (
  <PedidosHub fixedKind="contact" pageTitle="Contactos" />
);
export const PedidosOrcamentos = () => (
  <PedidosHub fixedKind="quote" pageTitle="Orçamentos" />
);
export const PedidosIA = () => (
  <PedidosHub fixedKind="ai_chat" pageTitle="Chats IA" />
);
export const PedidosAutorizacoes = () => (
  <PedidosHub fixedKind="permit" pageTitle="Autorizações de obras" />
);
export const PedidosDownloads = () => (
  <PedidosHub fixedKind="download" pageTitle="Downloads" />
);
export const PedidosCalculos = () => (
  <PedidosHub fixedKind="calculation" pageTitle="Cálculos guardados" />
);
