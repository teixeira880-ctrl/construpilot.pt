import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export const postalError = (error) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  if (Array.isArray(detail)) return "Verifique os contactos e confirme o preço antes do envio.";
  return "O serviço postal não responde. Verifique o acompanhamento antes de qualquer nova tentativa de envio.";
};

export const usePostalQuote = ({ open, token, form, mode, addressSource, valid }) => {
  const [result, setResult] = useState(null);
  const [retry, setRetry] = useState(0);
  const [clock, setClock] = useState(Date.now());
  const key = JSON.stringify({ token, form, mode, addressSource, retry });
  useEffect(() => {
    if (!open || !token || !valid) return;
    let active = true;
    const timer = setTimeout(async () => {
      try {
        const { data } = await api.post(`/radar/prospection/${token}/postal/quote`,
          { recipient: form, mode, address_source: addressSource }, { timeout: 45000 });
        if (active) setResult({ key, data });
      } catch (e) { if (active) setResult({ key, error: postalError(e), errorCode: e?.response?.data?.detail?.code }); }
    }, 600);
    return () => { active = false; clearTimeout(timer); };
  }, [open, token, key, valid, addressSource, form, mode]); // stale results never authorize sending
  useEffect(() => {
    if (!open) return;
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [open]);
  const current = result?.key === key && open && valid ? result : null;
  const expired = current?.data && Date.parse(current.data.expires_at) <= clock;
  return { price: !expired ? current?.data : null,
    errorCode: current?.errorCode,
    error: expired ? "Este preço expirou. Atualize-o antes de confirmar." : current?.error,
    loading: open && valid && !current, refresh: () => setRetry((value) => value + 1) };
};