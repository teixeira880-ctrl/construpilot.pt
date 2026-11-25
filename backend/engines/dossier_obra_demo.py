"""Obra fictícia de demonstração do Dossier de Obra («Moradia em L»).

Só é criada fora de produção (verificado na rota). Todos os registos ficam marcados `demo: True` e o nome
da obra indica «exemplo demonstrativo». Nenhuma medida, preço ou material aqui é real.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(p: str) -> str:
    return f"{p}_{secrets.token_hex(6)}"


async def seed(db, user: dict) -> dict:
    uid = user["user_id"]
    cid = "cht_" + secrets.token_hex(6)
    now = _now()
    await db.chantiers.insert_one({"chantier_id": cid, "user_id": uid, "name": "Moradia em L (exemplo demonstrativo)", "client_id": None,
                                   "client_name": "Cliente fictício", "address": "Rua Exemplo, 1", "postal_code": "1750-000", "city": "Lisboa",
                                   "status": "en_cours", "notes": "Dados fictícios para demonstração do dossier de obra.", "demo": True,
                                   "created_at": now, "updated_at": now})
    L = {k: _id("loc") for k in ("moradia", "p0", "p1", "wc", "fn")}
    locations = [
        {"location_id": L["moradia"], "kind": "edificio", "name": "Moradia em L", "parent_id": None},
        {"location_id": L["p0"], "kind": "piso", "name": "Piso 0", "parent_id": L["moradia"]},
        {"location_id": L["p1"], "kind": "piso", "name": "Piso 1", "parent_id": L["moradia"]},
        {"location_id": L["wc"], "kind": "zona", "name": "Casa de banho", "parent_id": L["p1"]},
        {"location_id": L["fn"], "kind": "zona", "name": "Fachada norte", "parent_id": L["moradia"]},
    ]
    enabled = ["implantacao", "paredes", "revest_exteriores", "revest_interiores", "coberturas", "caixilharias",
               "estruturas", "agua", "residuais", "eletricidade", "climatizacao", "termica"]
    await db.dossier_obra_configs.insert_one({"chantier_id": cid, "user_id": uid, "global_phase": "execucao", "enabled": enabled, "hidden": [],
                                              "custom": [], "locations": locations, "next_action": "", "started_mid_way": True, "demo": True,
                                              "created_at": now, "updated_at": now})
    for key, status, stage, nxt in (("revest_exteriores", "em_preparacao", "executar", "Confirmar o suporte antes de assentar a cerâmica."),
                                    ("agua", "em_curso", "validar", "Registar a verificação antes de propor o fecho das paredes."),
                                    ("paredes", "a_validar", "executar", "")):
        await db.dossier_obra_specialties.insert_one({"chantier_id": cid, "user_id": uid, "key": key, "status": status, "stage": stage,
                                                      "responsible": "", "next_step": nxt, "history": [], "demo": True,
                                                      "created_at": now, "updated_at": now})
    hist = [{"at": now, "by": "exemplo", "action": "criado"}]

    def item(**kw):
        base = {"item_id": _id("itm"), "chantier_id": cid, "user_id": uid, "element": "", "detail": "", "status": "por_fazer", "stage": None,
                "phase": "execucao", "location_id": None, "source": "manual", "validation": "por_confirmar", "measurement": None,
                "quantities": {}, "layers": None, "ref": None, "revision": "", "related_specialty": None, "approved": False,
                "needs_review": False, "history": list(hist), "demo": True, "created_at": now, "updated_at": now}
        base.update(kw)
        return base

    items = [
        item(specialty="revest_exteriores", element="Cerâmica exterior", kind="medicao", title="Área de cerâmica — fachada norte",
             location_id=L["fn"], source="extraido", validation="confirmado", status="concluido", revision="P03",
             measurement={"document": "Fachadas_P03.pdf (fictício)", "revision": "P03", "page": "2", "element": "Alçado norte, pano entre cotas",
                          "scale": "1:100", "method": "Área de polígono descontando vãos", "quantity": 84.0, "unit": "m²"},
             quantities={"medida": 84.0}),
        item(specialty="revest_exteriores", element="Cerâmica exterior", kind="material", title="Revestimento cerâmico exterior (por confirmar)",
             location_id=L["fn"], source="inferido", validation="por_confirmar", revision="P03",
             detail="A trama da planta sugere um revestimento cerâmico. Confirmar material e composição antes de calcular a compra.",
             layers=[{"order": 1, "name": "Suporte", "material": "", "source": "inferido", "validation": "por_confirmar", "reference": "", "note": ""},
                     {"order": 2, "name": "Regularização", "material": "", "source": "inferido", "validation": "por_confirmar", "reference": "", "note": ""},
                     {"order": 3, "name": "Impermeabilização", "material": "Membrana cimentícia (exemplo)", "source": "extraido", "validation": "confirmado",
                      "reference": "Fachadas_P03.pdf · legenda", "note": ""},
                     {"order": 4, "name": "Colagem", "material": "", "source": "inferido", "validation": "por_confirmar", "reference": "", "note": ""},
                     {"order": 5, "name": "Cerâmica", "material": "Cerâmica (trama da planta)", "source": "inferido", "validation": "por_confirmar",
                      "reference": "Fachadas_P03.pdf · página 2", "note": "Trama detetada: confirmar material e composição."}]),
        item(specialty="revest_exteriores", element="Cerâmica exterior", kind="pendencia", title="Validar impermeabilização", status="pendente", location_id=L["fn"]),
        item(specialty="revest_exteriores", element="Cerâmica exterior", kind="pendencia", title="Confirmar passagens técnicas", status="pendente",
             location_id=L["fn"], related_specialty="agua"),
        item(specialty="revest_exteriores", element="Cerâmica exterior", kind="tarefa", title="Aprovar amostra do material", status="por_fazer", location_id=L["fn"]),
        item(specialty="agua", kind="tarefa", title="Concluir instalação", status="concluido", validation="confirmado", location_id=L["wc"]),
        item(specialty="agua", kind="verificacao", title="Registar verificação (ensaio de estanquidade)", status="pendente", location_id=L["wc"]),
        item(specialty="agua", kind="tarefa", title="Adicionar fotografias da instalação", status="por_fazer", location_id=L["wc"]),
        item(specialty="agua", kind="tarefa", title="Validar fecho das paredes", status="bloqueado", location_id=L["wc"],
             detail="Aguarda o registo da verificação.", related_specialty="paredes"),
        item(specialty="agua", kind="documento", title="Rede_Aguas_P02.pdf (fictício)", status="concluido", validation="confirmado", revision="P02",
             source="extraido"),
        item(specialty="paredes", kind="tarefa", title="Fecho das paredes da casa de banho", status="por_fazer", location_id=L["wc"]),
    ]
    for it in items:
        await db.dossier_obra_items.insert_one(dict(it))
    for f, r, t, status in (("agua", "verificar_antes_de", "paredes", "confirmada"), ("agua", "verificar_antes_de", "revest_interiores", "confirmada"),
                            ("revest_exteriores", "partilha_com", "agua", "confirmada"), ("revest_exteriores", "partilha_com", "termica", "proposta")):
        await db.dossier_obra_dependencies.insert_one({"dep_id": _id("dep"), "chantier_id": cid, "user_id": uid, "from_specialty": f, "relation": r,
                                                       "to_specialty": t, "note": "Exemplo demonstrativo", "status": status,
                                                       "confirmed_by": "exemplo" if status == "confirmada" else None, "demo": True, "created_at": now})
    return {"chantier_id": cid, "name": "Moradia em L (exemplo demonstrativo)", "locations": {k: v for k, v in L.items()}}
