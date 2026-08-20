import { useEffect, useState, useCallback } from "react";

const DISMISS_KEY = "cp_pwa_dismissed_at";
const DISMISS_DAYS = 7;

export const isStandalone = () =>
  window.matchMedia("(display-mode: standalone)").matches ||
  window.navigator.standalone === true;

export const isIOS = () =>
  /iphone|ipad|ipod/i.test(window.navigator.userAgent) && !window.MSStream;

const recentlyDismissed = () => {
  const at = Number(localStorage.getItem(DISMISS_KEY) || 0);
  return at && Date.now() - at < DISMISS_DAYS * 864e5;
};

// Hook partagé : gère l'événement d'installation PWA (Android/desktop) + détection iOS.
export const usePwaInstall = () => {
  const [deferred, setDeferred] = useState(null);
  const [canInstall, setCanInstall] = useState(false); // beforeinstallprompt reçu
  const [ios, setIos] = useState(false);
  const [installed, setInstalled] = useState(isStandalone());
  const [dismissed, setDismissed] = useState(recentlyDismissed());

  useEffect(() => {
    if (installed) return;
    const onBeforeInstall = (e) => {
      e.preventDefault();
      setDeferred(e);
      setCanInstall(true);
    };
    const onInstalled = () => setInstalled(true);
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onInstalled);
    if (isIOS()) setIos(true);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, [installed]);

  const install = useCallback(async () => {
    if (!deferred) return;
    deferred.prompt();
    try { await deferred.userChoice; } catch { /* noop */ }
    setDeferred(null);
    setCanInstall(false);
  }, [deferred]);

  const dismiss = useCallback(() => {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
    setDismissed(true);
  }, []);

  // Rien à proposer si déjà installé, rejeté récemment, ou ni installable ni iOS
  const available = !installed && !dismissed && (canInstall || ios);

  return { available, canInstall, ios, installed, install, dismiss };
};
