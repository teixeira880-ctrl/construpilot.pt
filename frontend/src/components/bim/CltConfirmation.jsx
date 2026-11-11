import { useEffect, useMemo, useRef, useState } from "react";
import { confirmationDocument } from "./cltConfirmationDocument";

export default function CltConfirmation({ file, report }) {
  const frame = useRef(null);
  const [height, setHeight] = useState(900);
  const doc = useMemo(() => confirmationDocument(report.pages), [report]);

  useEffect(() => {
    const onResize = (event) => {
      if (event.source !== frame.current?.contentWindow || event.data?.type !== "clt-confirmation-height") return;
      const measured = event.data.height;
      if (Number.isFinite(measured)) setHeight(Math.min(3200, Math.max(480, measured)));
    };
    window.addEventListener("message", onResize);
    return () => window.removeEventListener("message", onResize);
  }, []);

  return <section className="grid gap-2">
    <p className="text-sm"><strong>{file.name}</strong> · Confirmações desta sessão de análise. Regista as referências antes de fechar a análise.</p>
    <iframe ref={frame} className="block w-full rounded border" title="Home A — confirmação de medições CLT"
      sandbox="allow-scripts allow-forms" referrerPolicy="no-referrer" height={height} srcDoc={doc} />
  </section>;
}
