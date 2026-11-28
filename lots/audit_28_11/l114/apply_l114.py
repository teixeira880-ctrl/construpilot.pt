"""Lot 114 (FR + PT) — /bim ne plante plus (« ReferenceError: atelierId is not defined »).

Cause exacte (diagnostic du serveur) : `atelierId` est lu dans le composant BimViewer (ligne ~39) mais utilisé dans
le sous-composant BimPlanViewer (lignes ~160-270), où il n'existe pas. Correctif : il est transmis en propriété.

Usage : python3 lots/l114/apply_l114.py <racine /app> <fr|pt>   (idempotent, marqueur CP-AUDIT-NUIT-6)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2] if len(sys.argv) > 2 else "fr"
MARK = "CP-AUDIT-NUIT-6"
rel = "frontend/src/pages/BimViewer.jsx"
p = root / rel
txt = p.read_text(encoding="utf-8")
OLD_CALL = "<BimPlanViewer key={`${planId || \"\"}:${page}:${query}`} planId={planId} page={page} query={query} onPageChange={changePage} />;"
NEW_CALL = ("<BimPlanViewer key={`${planId || \"\"}:${atelierId || \"\"}:${page}:${query}`} planId={planId} atelierId={atelierId} "
            "page={page} query={query} onPageChange={changePage} />;  // " + MARK)
OLD_SIG = "function BimPlanViewer({ planId, page, query, onPageChange }) {"
NEW_SIG = "function BimPlanViewer({ planId, atelierId, page, query, onPageChange }) {"
if MARK in txt:
    print("DÉJÀ      /bim : atelierId transmis à BimPlanViewer")
    sys.exit(0)
if txt.count(OLD_CALL) != 1 or txt.count(OLD_SIG) != 1:
    print("IGNORÉ    /bim : ancres absentes — envoyer la sortie de grep -n 'BimPlanViewer' " + rel)
    sys.exit(1)
p.write_text(txt.replace(OLD_CALL, NEW_CALL).replace(OLD_SIG, NEW_SIG), encoding="utf-8")
print(f"Lot 114 ({site}) — {MARK}\nOK        /bim : atelierId transmis à BimPlanViewer")
