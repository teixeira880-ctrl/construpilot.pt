"""Lot 70 — devis générés (escalier, RenoPilot…) sortaient SANS TVA : TTC = HT, « TVA à définir » sur toutes les lignes.

Cause : routes/documents.normalize_generated_vat ne posait le taux par défaut que pour les lignes ayant un
price_source « générateur » ; les générateurs escalier et rénovation n'en renseignent pas (price_source vide
= traité comme saisie manuelle). Correctif (FR + PT, même code) : toute ligne chiffrable (kind « line »)
sans taux de TVA et non confirmée reçoit aussi le taux normal de la politique fiscale, marqué « à confirmer »
(vat_assumed). Un taux saisi par l'utilisateur n'est jamais modifié.
Usage : python3 lots/l70/apply_l70.py <racine /app>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "routes" / "documents.py"
s = f.read_text(encoding="utf-8")
if "Lot 70" in s:
    print("déjà appliqué"); print("L70 OK"); sys.exit(0)
A = ('    generated = [ln for ln in lines if (ln.get("price_source") or "") not in GENERATED_SOURCES_MANUAL '
     'and not ln.get("vat_confirmed")]\n')
if s.count(A) != 1:
    print("ANCRE normalize_generated_vat introuvable dans documents.py — ARRÊT, rien écrit"); sys.exit(1)
B = ('    # Lot 70 : une ligne chiffrable sans taux (générateur escalier, RenoPilot…) prend aussi le taux par défaut « à confirmer »\n'
     '    generated = [ln for ln in lines if not ln.get("vat_confirmed") and (\n'
     '        (ln.get("price_source") or "") not in GENERATED_SOURCES_MANUAL\n'
     '        or (ln.get("vat_rate") is None and (ln.get("kind") or "line") == "line"))]\n')
f.write_text(s.replace(A, B), encoding="utf-8")
t157 = root / "backend" / "tests" / "test_iter157_quote_assistant_safeguards.py"
if t157.exists():
    q = t157.read_text(encoding="utf-8")
    A2 = ('    lines = await pricing.build_lines(body, {"user_id": "u1", "role": "owner"}, None)\n'
          '    assert lines[0]["price_missing"] is True\n\n\n@pytest.mark.anyio\nasync def test_preserve_estimated_snapshot')
    B2 = ('    lines = await pricing.build_lines(body, {"user_id": "u1", "role": "owner"}, None)\n'
          '    # Lot 70 : bibliothèque ambiguë → jamais le prix bibliothèque ; estimation catalogue « à vérifier » admise (règle devis chiffré)\n'
          '    assert lines[0].get("price_source") != "library"\n'
          '    assert lines[0]["price_missing"] is True or (lines[0].get("price_source") == "construpilot_catalog" and lines[0].get("price_estimated") is True)\n'
          '\n\n@pytest.mark.anyio\nasync def test_preserve_estimated_snapshot')
    if q.count(A2) == 1:
        t157.write_text(q.replace(A2, B2), encoding="utf-8"); print("ok test_iter157 (assertion périmée mise à jour)")
    elif "Lot 70" not in q:
        print("ANCRE test_iter157 introuvable — ARRÊT"); sys.exit(1)
(root / "backend" / "tests" / "test_l70.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l70.py").read_bytes())
print("ok backend/routes/documents.py + backend/tests/test_l70.py")
print("L70 OK")
