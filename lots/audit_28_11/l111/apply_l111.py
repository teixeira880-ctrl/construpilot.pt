"""Lot 111 (FR + PT) — audit de nuit du 28/11/2026, suite 2.

 1. Connexion : si le serveur répond une erreur passagère (HTTP 520/502/503, réseau) à /api/auth/me,
    l'utilisateur connecté était renvoyé sur /login (constaté en production pendant un redémarrage).
    Désormais : nouvel essai automatique (1 s, 2 s, 4 s, 8 s) avant de conclure ; seuls 401/403 déconnectent.
 2. DPGF : une colonne d'unité intitulée « U » (ou « Ut », « Un ») n'était pas reconnue → toutes les lignes
    passaient en « u » au lieu de m², ml… (ex. cloisons 120 m² chiffrées « 120 u »).

Usage : python3 lots/l111/apply_l111.py <racine /app> <fr|pt>   (idempotent, marqueur CP-AUDIT-NUIT-3)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2] if len(sys.argv) > 2 else "fr"
assert site in ("fr", "pt")
MARK = "CP-AUDIT-NUIT-3"
report = []


def replace(name, rel, old, new):
    p = root / rel
    if not p.exists():
        return report.append(f"ABSENT    {name}")
    txt = p.read_text(encoding="utf-8")
    if MARK in txt and new in txt:
        return report.append(f"DÉJÀ      {name}")
    if txt.count(old) != 1:
        return report.append(("IGNORÉ    " if old not in txt else "AMBIGU    ") + name)
    p.write_text(txt.replace(old, new), encoding="utf-8")
    report.append(f"OK        {name}")


replace("1 Connexion : erreurs passagères ≠ déconnexion", "frontend/src/context/AuthContext.jsx",
        """  const checkAuth = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      try { localStorage.setItem("construpilot_session", "1"); } catch {}
    } catch (error) {
      if ([401, 403].includes(error.response?.status)) {
        setUser(null);
        try { localStorage.removeItem("construpilot_session"); } catch {}
      }
    } finally {
      setLoading(false);
    }
  }, []);""",
        f"""  const checkAuth = useCallback(async (attempt = 0) => {{
    try {{
      const {{ data }} = await api.get("/auth/me");
      setUser(data);
      try {{ localStorage.setItem("construpilot_session", "1"); }} catch {{}}
      setLoading(false);
    }} catch (error) {{
      const status = error.response?.status;
      if ([401, 403].includes(status)) {{
        setUser(null);
        try {{ localStorage.removeItem("construpilot_session"); }} catch {{}}
        setLoading(false);
        return;
      }}
      // {MARK} : erreur passagère (5xx, 520 Cloudflare, réseau) → on réessaie avant de conclure,
      // sinon un utilisateur connecté est renvoyé sur /login pendant un redémarrage du serveur.
      if (attempt < 4) {{
        setTimeout(() => checkAuth(attempt + 1), 1000 * 2 ** attempt);
        return;
      }}
      setLoading(false);
    }}
  }}, []);""")

replace("2 DPGF : colonne « U » reconnue", "backend/engines/dpgf_engine.py",
        '            elif "unit" not in cols and any(val == k or val.startswith(k) for k in _UNIT):\n',
        '            elif "unit" not in cols and (any(val == k or val.startswith(k) for k in _UNIT)\n'
        f'                                         or val in ("u", "ut", "un", "unités", "unites")):  # {MARK}\n')

print(f"Lot 111 ({site}) — {MARK}")
print("\n".join(report))
sys.exit(1 if any(r.startswith("AMBIGU") for r in report) else 0)
