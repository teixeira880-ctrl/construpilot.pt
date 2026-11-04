"""Lot 84 (FR + PT) — import d'un grand plan PDF (A0) : le serveur tombait (réponse vide 520).

Constat (production .pt, 04/11, import réel « AES … Plan coffrage PH R+4 », 1 page 3370×2591 pt ≈ A0+) :
POST /takeoffs/upload → 202, puis /upload-jobs/… et /takeoffs → 520 (processus backend redémarré) ; la tâche
reste « processing » pour toujours et l'écran d'import se referme sans plan. Cause : process_pdf rendait chaque
page à 200 dpi AVANT de la réduire (9 361 × 7 197 px ≈ 200 Mo RGB, ×3 avec la copie PIL et la réduction) → mémoire.
Correctif : la page est rendue directement à la taille utile (côté max ≤ 1,25 × max_side, plancher 36 dpi). Les
petites pages (A3/A4) gardent exactement 200 dpi ; l'échelle (dpi effectif) reste cohérente car elle est
recalculée à partir du dpi réellement utilisé.
Usage : python3 lots/l84/apply_l84.py <racine /app>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "plan_processor.py"
s = f.read_text(encoding="utf-8")
if "Lot 84" in s:
    print("déjà appliqué"); print("L84 OK"); sys.exit(0)
R = [("        pix = page.get_pixmap(dpi=render_dpi, alpha=False)\n",
      "        # Lot 84 : rendu direct à la taille utile (un A0 à 200 dpi saturait la mémoire du serveur)\n"
      "        page_dpi = int(min(render_dpi, max(36, 72 * max_side * 1.25 // max(page.rect.width, page.rect.height, 1.0))))\n"
      "        pix = page.get_pixmap(dpi=page_dpi, alpha=False)\n"),
     ("render_dpi * ratio / 72", "page_dpi * ratio / 72"),
     ('"dpi": round(render_dpi * ratio, 2),', '"dpi": round(page_dpi * ratio, 2),')]
for a, _ in R:
    if s.count(a) != 1:
        print("ANCRE introuvable — ARRÊT, rien écrit:", a.strip()[:60]); sys.exit(1)
for a, b in R:
    s = s.replace(a, b)
f.write_text(s, encoding="utf-8")
(root / "backend" / "tests" / "test_l84.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l84.py").read_bytes())
print("ok backend/engines/plan_processor.py + backend/tests/test_l84.py")
print("L84 OK")
