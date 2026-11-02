"""Dados demo « Moradia Ferreira » (.pt): planta de arquiteto fictícia, levantamento exato, orçamento real.

A planta vem de scripts/demo_plan/make_plan_pt.py (geometria em metros → PDF + PNG + compartimentos).
O levantamento sai diretamente dessa geometria; os preços vêm do catálogo ConstruPilot
(engines/catalog.py, acabamento « standard » = material std + mão de obra) e os totais de
routes/documents._compute_totals — exatamente o que a aplicação calcularia.

Uso (programador, uma vez): python3 scripts/build_demo_ferreira_pt.py
→ escreve data/demo_dossier_pt.json (placeholder __PRO_UID__ para o utilizador demo Pro).
"""
from __future__ import annotations

import ast
import base64
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engines.catalog import LOTS_BY_KEY  # noqa: E402

OUT_JSON = ROOT / "data" / "demo_dossier_pt.json"
PLAN_DIR = ROOT / "assets" / "demo_plans"
UID = "__PRO_UID__"
VAT = 23.0


def compute_totals(lines, deposit_pct=0.0):
    """Cópia fiel de routes.documents._compute_totals (sem dependência da base de dados)."""
    src = (ROOT / "routes" / "documents.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_compute_totals")
    ns: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "documents.py", "exec"), ns)
    return ns["_compute_totals"](lines, deposit_pct)


def price(key):
    lot = LOTS_BY_KEY[key]
    return round(lot["mat_std"] + lot["labour"], 2)


TERMS = "Adjudicação: 30 % na assinatura, 40 % a meio da obra, restante na receção. Orçamento válido por 3 meses."
NOTE = ("Quantidades obtidas do levantamento automático da planta « Moradia Ferreira — R/C » (revisão A). "
        "IVA à taxa normal de 23 %. A taxa reduzida de 6 % (verba 2.27 da Lista I do CIVA) pode aplicar-se a "
        "obras de remodelação em habitação — a confirmar caso a caso.")
CLIENT = {"first_name": "Ana", "last_name": "Ferreira", "company": "", "email": "ana.ferreira@example.com",
          "phone": "912 345 678", "address": "Rua das Amendoeiras, 12", "postal_code": "2750-310", "city": "Cascais"}
TILE = ("room_sejour", "room_entree", "room_degag", "room_wc", "room_cellier", "room_sdb")
WOOD = ("room_ch1", "room_ch2", "room_ch3")
NOW = "2026-10-28T09:30:00+00:00"


def build_main(plan_png, rooms, meta):
    cli_id, cht_id, plan_id, doc_id = "cli_ferreira_pt", "cht_ferreira_pt", "plan_ferreira_pt", "doc_ferreira_quote_pt"
    client = {"client_id": cli_id, "user_id": UID, **CLIENT, "siret": "", "created_at": NOW, "updated_at": NOW}
    chantier = {"chantier_id": cht_id, "user_id": UID, "name": "Moradia Ferreira — remodelação completa",
                "client_id": cli_id, "address": CLIENT["address"], "postal_code": CLIENT["postal_code"],
                "city": CLIENT["city"], "status": "prospect",
                "notes": "Moradia térrea T3 de 116 m². Remodelação interior completa antes da mudança.",
                "client_name": "Ana Ferreira", "created_at": NOW, "updated_at": NOW}
    ppm = meta["pixels_per_meter"]
    p1 = rooms[0]["points"][0]
    takeoff = {
        "plan_id": plan_id, "user_id": UID, "project_id": None, "chantier_id": cht_id,
        "filename": "planta-moradia-ferreira-rc.png", "size_bytes": len(plan_png), "kind": "image", "page_count": 1,
        "detected_scale_denominator": 50,
        "pages": [{"index": 0, "width_px": meta["width_px"], "height_px": meta["height_px"], "dpi": 120,
                   "vectors": [], "text_blocks": [], "dimensions_count": 20, "raw_text_length": 0,
                   "source_mime": "image/png", "original_width_px": meta["width_px"],
                   "original_height_px": meta["height_px"], "image_png_b64": base64.b64encode(plan_png).decode()}],
        "calibrations": {"0": {"pixels_per_meter": ppm, "meters_per_pixel": round(1 / ppm, 6),
                               "reference_pixel_distance": round(12.6 * ppm, 1), "reference_real_distance_m": 12.6,
                               "method": "two_points", "confidence": 0.98,
                               "p1": p1, "p2": [round(p1[0] + 12.6 * ppm, 1), p1[1]], "created_at": NOW}},
        "measurements": [], "ai_analysis": None,
        "rooms": [{**r, "created_at": NOW} for r in rooms],
        "created_at": NOW, "updated_at": NOW,
    }
    by = {r["room_id"]: r for r in rooms}
    floor = sum(r["surface_m2"] for r in rooms)
    walls_ceiling = sum(r["wall_area_net_m2"] + r["ceiling_area_m2"] for r in rooms)
    perim = sum(r["perimeter_m"] for r in rooms)
    doors = sum(1 for r in rooms for o in r["openings"] if o["type"] == "porte")
    raw = [
        ("Remoção dos revestimentos existentes (pavimentos, azulejos, papel de parede)", "m²", floor, price("demolition"), "Demolição"),
        ("Pladur: revestimento de paredes e reparação de tetos (gesso cartonado)", "m²", walls_ceiling, price("placo"), "Pladur"),
        ("Pintura de paredes e tetos, 2 demãos (primário + acabamento)", "m²", walls_ceiling, price("peinture"), "Pintura"),
        ("Pavimento porcelânico 60×60 (sala, entrada, corredor, WC, lavandaria, casa de banho)", "m²",
         sum(by[k]["surface_m2"] for k in TILE), price("carrelage"), "Pavimentos"),
        ("Soalho flutuante em carvalho (quartos 1, 2 e 3)", "m²", sum(by[k]["surface_m2"] for k in WOOD), price("parquet"), "Pavimentos"),
        ("Rodapés a condizer, fornecidos e aplicados", "ml", perim - 1.8 * doors, 11.0, "Pavimentos"),
        ("Eletricidade: remodelação da instalação conforme RTIEBT, quadro, tomadas e pontos de luz", "m²", floor, price("electricite"), "Eletricidade"),
        ("Ventilação mecânica com bocas higrorreguláveis (cozinha, casa de banho, WC, lavandaria)", "m²", floor, price("ventilation"), "Ventilação"),
        ("Casa de banho completa: base de duche, móvel com lavatório, revestimento cerâmico, canalização", "m²",
         by["room_sdb"]["surface_m2"], price("salle_de_bain"), "Casa de banho"),
        ("Remoção de entulho para destino autorizado e limpeza final", "m²", floor, price("dechets"), "Resíduos"),
    ]
    lines = [{"designation": d, "unit": u, "qty": round(q, 2), "unit_price_ht": p, "vat_rate": VAT, "category": c}
             for d, u, q, p, c in raw]
    quote = {
        "doc_id": doc_id, "user_id": UID, "doc_type": "quote", "number": "DEV-2026-0007",
        "title": "Orçamento — Remodelação completa da Moradia Ferreira (planta R/C)",
        "client_id": cli_id, "client": {"client_id": cli_id, "siret": "", **CLIENT},
        "chantier_id": cht_id, "status": "sent", "signed": False, "lines": lines, "notes": NOTE,
        "payment_terms": TERMS, "deposit_pct": 30.0, "totals": compute_totals(lines, 30.0),
        "issue_date": NOW, "due_date": None, "source": "takeoff", "plan_id": plan_id, "lang": "pt",
        "created_at": NOW, "updated_at": NOW,
    }
    return {"clients": [client], "chantiers": [chantier], "plans_takeoff": [takeoff], "pro_documents": [quote]}


EXTRA = [
    {"key": "tejo", "client": {"first_name": "Rui", "last_name": "Costa", "company": "Imobiliária Tejo, Lda.",
     "email": "geral@imotejo.example", "phone": "213 456 789", "address": "Avenida da República, 50",
     "postal_code": "1050-196", "city": "Lisboa"},
     "chantier": "Escritórios Avenida — renovação", "status": "prospect", "number": None, "doc_status": "draft",
     "title": "Orçamento — Pintura e pavimentos dos escritórios (2.º andar)", "date": "2026-10-30T14:00:00+00:00",
     "lines": [("Pintura de paredes e tetos, 2 demãos", "m²", 240, "peinture", "Pintura"),
               ("Pavimento vinílico em réguas, colado", "m²", 85, "parquet", "Pavimentos"),
               ("Remoção de entulho e limpeza", "m²", 85, "dechets", "Resíduos")]},
    {"key": "sousa", "client": {"first_name": "Pedro", "last_name": "Sousa", "company": "",
     "email": "pedro.sousa@example.com", "phone": "934 567 120", "address": "Rua do Almada, 120",
     "postal_code": "4050-031", "city": "Porto"},
     "chantier": "Casa de banho Sousa", "status": "en_cours", "number": "DEV-2026-0005", "doc_status": "signed",
     "title": "Orçamento — Remodelação de casa de banho (6 m²)", "date": "2026-10-12T10:00:00+00:00",
     "lines": [("Remoção de louças sanitárias e azulejos existentes", "m²", 6, "demolition", "Demolição"),
               ("Casa de banho completa: base de duche, móvel com lavatório, revestimento cerâmico, canalização", "m²", 6, "salle_de_bain", "Casa de banho"),
               ("Ventilação: boca de extração higrorregulável na casa de banho", "m²", 6, "ventilation", "Ventilação")],
     "invoice": {"number": "FAC-2026-0009"}},
]


def build_extra():
    out = {"clients": [], "chantiers": [], "pro_documents": []}
    for e in EXTRA:
        k = f"{e['key']}_pt"
        cli = {"client_id": f"cli_{k}", "user_id": UID, **e["client"], "siret": "", "created_at": e["date"], "updated_at": e["date"]}
        out["clients"].append(cli)
        out["chantiers"].append({"chantier_id": f"cht_{k}", "user_id": UID, "name": e["chantier"], "client_id": cli["client_id"],
            "address": e["client"]["address"], "postal_code": e["client"]["postal_code"], "city": e["client"]["city"],
            "status": e["status"], "notes": "",
            "client_name": e["client"]["company"] or f"{e['client']['first_name']} {e['client']['last_name']}",
            "created_at": e["date"], "updated_at": e["date"]})
        lines = [{"designation": d, "unit": u, "qty": q, "unit_price_ht": price(lot), "vat_rate": VAT, "category": c}
                 for d, u, q, lot, c in e["lines"]]
        snap = {"client_id": cli["client_id"], "siret": "", **e["client"]}
        q = {"doc_id": f"doc_{k}_quote", "user_id": UID, "doc_type": "quote", "number": e["number"], "title": e["title"],
             "client_id": cli["client_id"], "client": snap, "chantier_id": f"cht_{k}", "status": e["doc_status"],
             "signed": e["doc_status"] == "signed", "lines": lines, "notes": "", "payment_terms": TERMS,
             "deposit_pct": 30.0, "totals": compute_totals(lines, 30.0),
             "issue_date": e["date"] if e["number"] else None, "due_date": None, "source": "manual", "lang": "pt",
             "created_at": e["date"], "updated_at": e["date"]}
        out["pro_documents"].append(q)
        inv = e.get("invoice")
        if inv:
            # Mesmo formato que routes.documents (fatura de adiantamento a partir de um orçamento assinado).
            num = q["number"]
            il = [{"designation": f"Adiantamento 30% sobre o orçamento N.º{num}", "description": q["title"],
                   "unit": "forfait", "qty": 1, "unit_price_ht": round(q["totals"]["ht"] * 0.30, 2),
                   "vat_rate": VAT, "category": "Adiantamento"}]
            t = compute_totals(il, 0)
            inv_id = f"doc_{k}_inv"
            q["deposit_invoice_id"] = inv_id
            out["pro_documents"].append({
                "doc_id": inv_id, "user_id": UID, "doc_type": "invoice", "number": inv["number"],
                "title": f"Fatura de adiantamento 30% — orçamento N.º{num}",
                "client_id": cli["client_id"], "client": snap, "chantier_id": f"cht_{k}", "status": "paid",
                "lines": il, "notes": f"Fatura de adiantamento de 30% correspondente ao orçamento N.º{num}.",
                "payment_terms": TERMS, "deposit_pct": 0, "totals": t,
                "payments": [{"payment_id": "pay_demo_sousa", "amount": t["ttc"], "method": "transferência",
                              "date": "2026-10-20T09:00:00+00:00", "note": ""}],
                "paid": t["ttc"], "remaining_due": 0.0,
                "issue_date": "2026-10-14T09:00:00+00:00", "due_date": "2026-11-13T09:00:00+00:00",
                "source": "deposit", "parent_doc_id": q["doc_id"], "source_quote_id": q["doc_id"],
                "source_quote_number": num, "deposit_pct_of_quote": 30.0, "lang": "pt",
                "created_at": "2026-10-14T09:00:00+00:00", "updated_at": "2026-10-20T09:00:00+00:00"})
    return out


def main():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "demo_plan" / "make_plan_pt.py"), str(PLAN_DIR)], check=True)
    geo = json.loads((PLAN_DIR / "rooms_ferreira_pt.json").read_text(encoding="utf-8"))["pt"]
    png = (PLAN_DIR / "plan-moradia-ferreira-pt.png").read_bytes()
    data = build_main(png, geo["rooms"], geo["meta"])
    for coll, docs in build_extra().items():
        data[coll] = data.get(coll, []) + docs
    OUT_JSON.write_text(json.dumps({"pro": data}, ensure_ascii=False, indent=1), encoding="utf-8")
    q = data["pro_documents"][0]
    print(q["number"], q["totals"]["ht"], q["totals"]["ttc"])


if __name__ == "__main__":
    main()
