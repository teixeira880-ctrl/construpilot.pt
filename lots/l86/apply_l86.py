"""Lot 86 (FR + PT) — import d'un plan A0 : le serveur .pt tombait ENCORE après le Lot 84 (520).

Constat (production .pt, 04/11 18 h 04, Lot 84 en ligne) : nouvel import réel du plan AES A0 → 520 puis tâche
orpheline (close par le Lot 85). Mesure locale (RSS) : +200 Mo pendant le rendu d'une page A0 avec le Lot 84
(pixmap 1,25× + copie PIL + réduction + copie convert("RGB")). Le conteneur .pt a moins de marge que le .fr.
Correctif : rendu exactement à la taille servie (plus de réduction), image PIL sans copie (frombuffer sur la
pixmap), plus de copie convert("RGB") quand l'image est déjà RGB, libération immédiate de la pixmap.
Pages A3/A4 : inchangées (200 dpi).
Usage : python3 lots/l86/apply_l86.py <racine /app>   (Lot 84 requis ; idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "plan_processor.py"
s = f.read_text(encoding="utf-8")
if "Lot 86" in s:
    print("déjà appliqué"); print("L86 OK"); sys.exit(0)
if "Lot 84" not in s:
    print("Lot 84 absent — ARRÊT, rien écrit"); sys.exit(1)
R = [("72 * max_side * 1.25 // max(page.rect.width, page.rect.height, 1.0)",
      "72 * max_side // max(page.rect.width, page.rect.height, 1.0)"),
     ('        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)\n'
      '        img_b64, img_mime, fw, fh, ratio = _encode_preview(img, max_side=max_side)\n',
      '        # Lot 86 : rendu à la taille servie, image sans copie (frombuffer), pixmap libérée aussitôt\n'
      '        img = Image.frombuffer("RGB", (pix.width, pix.height), pix.samples_mv, "raw", "RGB", pix.stride, 1)\n'
      '        img_b64, img_mime, fw, fh, ratio = _encode_preview(img, max_side=max_side)\n'
      '        del img, pix\n'),
     ('    img.convert("RGB").save(jbuf, format="JPEG", quality=85, optimize=True)\n',
      '    (img if img.mode == "RGB" else img.convert("RGB")).save(jbuf, format="JPEG", quality=85, optimize=True)  # Lot 86 : pas de copie inutile\n')]
for a, _ in R:
    if s.count(a) != 1:
        print("ANCRE introuvable — ARRÊT, rien écrit:", a.strip()[:70]); sys.exit(1)
for a, b in R:
    s = s.replace(a, b)
f.write_text(s, encoding="utf-8")
(root / "backend" / "tests" / "test_l86.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l86.py").read_bytes())
print("ok backend/engines/plan_processor.py + backend/tests/test_l86.py")
print("L86 OK")
