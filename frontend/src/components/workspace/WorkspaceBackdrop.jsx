import { useEffect, useState } from "react";

const MOTION_KEY = "construpilot_background_paused";
const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

export function useWorkspaceMotion() {
  const [paused, setPaused] = useState(() => {
    try { return localStorage.getItem(MOTION_KEY) === "true"; } catch { return false; }
  });
  const [reduced, setReduced] = useState(() => window.matchMedia(REDUCED_MOTION).matches);
  useEffect(() => {
    const media = window.matchMedia(REDUCED_MOTION);
    const update = () => setReduced(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    try { localStorage.setItem(MOTION_KEY, String(paused)); } catch { /* Storage can be unavailable. */ }
  }, [paused]);
  return { paused, reduced, toggle: () => setPaused(value => !value) };
}

export function WorkspaceBackdrop({ paused }) {
  const [hidden, setHidden] = useState(() => document.hidden);
  useEffect(() => {
    const update = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  return <div className="workspace-backdrop" data-testid="workspace-backdrop" data-paused={paused || hidden} aria-hidden="true">
    <span className="workspace-halo workspace-halo-copper" />
    <span className="workspace-halo workspace-halo-sage" />
  </div>;
}
