/**
 * Botão de partilha por WhatsApp.
 *
 * - Usa `wa.me` universal (sem número = partilha genérica, utilizador escolhe
 *   contacto na app).
 * - Ícone SVG oficial WhatsApp inline (sem dependências novas).
 * - Mensagem URL-encoded, cor oficial #25D366 por omissão.
 *
 * Props:
 *   - url: string (link a partilhar)
 *   - mensagem: string | undefined (prefixo PT-PT; default "Orçamento ConstruPilot — veja aqui:")
 *   - variant: "primary" | "outline" (default "primary")
 *   - className: string
 */
export function BotaoWhatsApp({
  url,
  mensagem,
  variant = "primary",
  className = "",
  testid = "btn-whatsapp-share",
}) {
  if (!url) return null;
  const prefixo = mensagem || "Orçamento ConstruPilot — veja aqui:";
  const texto = encodeURIComponent(`${prefixo} ${url}`);
  const href = `https://wa.me/?text=${texto}`;
  const base =
    "inline-flex items-center gap-2 rounded-sm px-4 h-9 text-sm font-medium transition-colors whitespace-nowrap";
  const estilo =
    variant === "primary"
      ? "bg-[#25D366] text-white hover:bg-[#1ebe57]"
      : "border border-[#25D366] text-[#25D366] hover:bg-[#25D366]/10";
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={`${base} ${estilo} ${className}`}
      data-testid={testid}
      aria-label="Enviar por WhatsApp"
    >
      <svg
        viewBox="0 0 32 32"
        aria-hidden="true"
        width="18"
        height="18"
        fill="currentColor"
      >
        <path d="M16.004 3C9.374 3 4 8.374 4 15c0 2.37.69 4.577 1.88 6.44L4 29l7.74-1.84A12 12 0 0 0 16.004 27C22.63 27 28 21.627 28 15S22.63 3 16.004 3Zm0 21.818a9.84 9.84 0 0 1-5.014-1.37l-.36-.213-4.59 1.093 1.11-4.47-.236-.374A9.818 9.818 0 1 1 16.004 24.818Zm5.587-7.33c-.306-.153-1.806-.89-2.085-.991-.28-.102-.483-.153-.687.153-.204.306-.788.991-.966 1.195-.178.204-.356.23-.662.076-.306-.153-1.29-.475-2.457-1.515-.908-.81-1.52-1.81-1.698-2.116-.178-.306-.019-.472.134-.624.137-.137.306-.356.46-.534.153-.179.204-.306.306-.51.102-.204.051-.382-.025-.534-.076-.153-.687-1.657-.942-2.27-.248-.595-.5-.514-.687-.524l-.586-.01c-.204 0-.534.076-.814.382-.28.306-1.068 1.043-1.068 2.544s1.093 2.95 1.246 3.154c.153.204 2.153 3.284 5.218 4.603.73.316 1.3.504 1.743.645.733.233 1.4.2 1.927.121.588-.088 1.806-.738 2.062-1.451.254-.713.254-1.323.178-1.45-.076-.128-.28-.204-.586-.357Z" />
      </svg>
      Enviar por WhatsApp
    </a>
  );
}

export default BotaoWhatsApp;
