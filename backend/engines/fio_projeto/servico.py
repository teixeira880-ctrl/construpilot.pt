"""Fio do projeto — um só fio do desenho ao dossier final.

O projeto do Ateliê Arquiteto (``archi_projects``) é a única fonte da geometria. Cada etapa seguinte (BIM, estudo
térmico, plantas de execução, orçamento, DCE / caderno de encargos, imagens 3D e renders) fica LIGADA ao projeto com a
impressão digital da geometria em que foi feita. Se o desenho mudar depois, a etapa aparece como desatualizada: nada se
perde e nada é refeito em silêncio sobre uma geometria diferente.

Nada aqui é estimado: as quantidades vêm de ``derivar`` (o mesmo motor das plantas, do IFC e das medições).
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from engines.fio_projeto.lingua import LANG

COL = "fio_projetos"
COL_IMG = "fio_imagens"
MAX_IMAGENS = 40
MAX_BYTES = 6 * 1024 * 1024
MIMES = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"RIFF": "image/webp"}
TIPOS_IMAGEM = ("bim", "render", "foto", "planta", "outra")

# campo → é lista (várias versões ficam guardadas, a mais recente é a ativa)
LIGACOES: Dict[str, bool] = {
    "conversation_id": True, "bim_model_id": False, "bim_version": False, "thermal_study_id": True,
    "execution_study_id": True, "bet_study_id": True, "house_study_id": True, "quote_id": True, "dce_id": True,
}
ETAPAS = ("desenho", "bim", "termica", "execucao", "orcamento", "dce", "imagens", "dossier")
CAMPO_ETAPA = {"bim_model_id": "bim", "thermal_study_id": "termica", "execution_study_id": "execucao",
               "bet_study_id": "execucao", "house_study_id": "execucao", "quote_id": "orcamento", "dce_id": "dce"}

TXT = {
    "pt": {
        "desenho": "Desenho (Ateliê)", "bim": "Maquete BIM", "termica": "Estudo térmico", "execucao": "Plantas de execução / engenharia",
        "orcamento": "Orçamento", "dce": "Caderno de encargos / DCE", "imagens": "Imagens 3D e renders", "dossier": "Dossier final",
        "desatualizado": "feito sobre uma versão anterior do desenho — refazer",
        "nao_encontrado": "Projeto não encontrado.", "campo": "Ligação desconhecida.", "valor": "Identificador inválido.",
        "img_tipo": "Formato de imagem não suportado (PNG, JPEG ou WebP).", "img_grande": "Imagem demasiado grande (máx. 6 MB).",
        "img_max": "Limite de imagens do projeto atingido (40).", "img_nao": "Imagem não encontrada.",
        "titulo_dossier": "Dossier do projeto", "gerado": "Gerado pela ConstruPilot em", "impressao": "Impressão digital da geometria",
        "areas": "Quadro de áreas", "piso": "Piso", "bruta": "Área bruta", "util": "Área útil", "total": "Total",
        "envolvente": "Envolvente", "fachada": "Fachada: área bruta {b} m², vãos {v} m², área líquida {l} m²",
        "cobertura": "Cobertura: {t}, {a} m² ({i}°)", "paredes": "Paredes por tipo (camadas do interior para o exterior)",
        "ext": "exterior", "int": "interior", "vaos": "Mapa de vãos", "etapas": "Seguimento do projeto",
        "feito": "feito", "por_fazer": "por fazer", "ligado": "ligado", "imagem": "Imagem", "avisos": "Avisos do modelo",
        "pranchas": "Peças desenhadas", "sem_pranchas": "As peças desenhadas não puderam ser juntadas a este dossier.",
        "nota": ("Medições geométricas do modelo único do projeto (sem ratios, sem estimativas). Os estudos de especialidade "
                 "e o orçamento indicados acima foram feitos sobre a geometria cuja impressão digital está registada."),
    },
    "fr": {
        "desenho": "Dessin (Atelier)", "bim": "Maquette BIM", "termica": "Étude thermique", "execucao": "Plans d'exécution / ingénierie",
        "orcamento": "Devis", "dce": "DCE (CCTP + DPGF)", "imagens": "Images 3D et rendus", "dossier": "Dossier final",
        "desatualizado": "réalisé sur une version antérieure du dessin — à refaire",
        "nao_encontrado": "Projet introuvable.", "campo": "Lien inconnu.", "valor": "Identifiant invalide.",
        "img_tipo": "Format d'image non pris en charge (PNG, JPEG ou WebP).", "img_grande": "Image trop lourde (6 Mo max.).",
        "img_max": "Nombre maximal d'images du projet atteint (40).", "img_nao": "Image introuvable.",
        "titulo_dossier": "Dossier du projet", "gerado": "Généré par ConstruPilot le", "impressao": "Empreinte de la géométrie",
        "areas": "Tableau des surfaces", "piso": "Niveau", "bruta": "Surface de plancher brute", "util": "Surface utile", "total": "Total",
        "envolvente": "Enveloppe", "fachada": "Façade : surface brute {b} m², baies {v} m², surface nette {l} m²",
        "cobertura": "Toiture : {t}, {a} m² ({i}°)", "paredes": "Murs par type (couches de l'intérieur vers l'extérieur)",
        "ext": "extérieur", "int": "intérieur", "vaos": "Tableau des menuiseries", "etapas": "Suivi du projet",
        "feito": "fait", "por_fazer": "à faire", "ligado": "lié", "imagem": "Image", "avisos": "Avertissements du modèle",
        "pranchas": "Pièces graphiques", "sem_pranchas": "Les pièces graphiques n'ont pas pu être jointes à ce dossier.",
        "nota": ("Métrés géométriques de la maquette unique du projet (sans ratios, sans estimation). Les études et le devis "
                 "indiqués ci-dessus ont été réalisés sur la géométrie dont l'empreinte est enregistrée."),
    },
}


def t(chave: str) -> str:
    return TXT.get(LANG, TXT["pt"]).get(chave, chave)


class ErroFio(ValueError):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status
        self.msg = msg


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def impressao_geometria(m: Dict[str, Any]) -> str:
    """Impressão digital estável do modelo: muda se e só se a geometria/composição mudar."""
    txt = json.dumps(m, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------------------- ateliê (fonte única)
def _aa():
    from routes import atelier_archi as AA   # o mesmo código que serve as plantas, o IFC e o DCE
    return AA


def _traduzir(x: Any) -> Any:
    AA = _aa()
    I = getattr(AA, "I", None)
    f = getattr(I, "traduzir", None) if I is not None else None
    if f is None:
        return x
    try:
        return f(x)
    except Exception:  # noqa: BLE001 — tradução nunca impede a leitura
        return x


async def carregar(user: Dict[str, Any], pid: str) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    from fastapi import HTTPException
    from fastapi.concurrency import run_in_threadpool
    AA = _aa()
    try:
        p = await AA._projet(pid, user["user_id"])
    except HTTPException as e:
        raise ErroFio(e.status_code, t("nao_encontrado")) from e
    m = AA._modele(p)
    der = await run_in_threadpool(AA.EP.derivar, m)
    return p, m, der


def resumo(p: Dict[str, Any], m: Dict[str, Any], der: Dict[str, Any]) -> Dict[str, Any]:
    med = der.get("medicoes") or {}
    tipos = m.get("tipos_parede") or {}
    paredes = []
    for pt in med.get("por_tipo") or []:
        paredes.append({"tipo": pt.get("tipo"), "nome": pt.get("nome"), "exterior": bool((tipos.get(pt.get("tipo")) or {}).get("exterior")),
                        "comprimento_liquido_m": pt.get("comprimento_liquido_m"), "area_liquida_m2": pt.get("area_liquida_m2"),
                        "camadas": [{"material": c.get("material"), "esp_m": c.get("esp_m"), "area_m2": c.get("area_m2"),
                                     "volume_m3": c.get("volume_m3")} for c in pt.get("camadas") or []]})
    vaos = [{**{k: v for k, v in linha.items() if k != "ids"}, "quantidade": len(linha.get("ids") or [])}
            for linha in med.get("mapa_vaos") or []]
    out = {
        "projet_id": p.get("projet_id"), "titulo": p.get("titre"), "morada": p.get("adresse"), "dono_obra": p.get("maitre_ouvrage"),
        "programa": (p.get("programme") or "")[:2000], "atualizado_em": p.get("updated_at"),
        "geometria": impressao_geometria(m),
        "quadro_areas": med.get("quadro_areas") or [], "totais": med.get("totais") or {},
        "area_implantacao_m2": med.get("area_implantacao_m2"), "fachada": med.get("fachada") or {},
        "cobertura": med.get("cobertura") or {}, "paredes_por_tipo": paredes, "vaos": vaos,
        "lajes": med.get("lajes") or [], "escadas": med.get("escadas") or [], "acabamentos": med.get("acabamentos") or [],
        "exteriores": med.get("exteriores") or [], "objetos": med.get("objetos") or [],
        "divisoes": [{"nome": d.get("nome"), "piso": d.get("piso"), "area_m2": d.get("area_m2")} for d in med.get("divisoes") or []],
        "erros": der.get("erros") or [], "avisos": der.get("avisos") or [],
        "convencao": med.get("convencao"),
    }
    return _traduzir(out)


# ------------------------------------------------------------------------------- fio (ligações)
def _etapas(fio: Dict[str, Any], geometria: str, n_imagens: int, tem_dce: bool) -> List[Dict[str, Any]]:
    ult: Dict[str, Dict[str, Any]] = {}
    for lig in fio.get("ligacoes") or []:
        e = CAMPO_ETAPA.get(lig.get("campo"))
        if e:
            ult[e] = lig                                   # a última ligação de cada etapa é a ativa
    out = [{"etapa": "desenho", "nome": t("desenho"), "feito": True, "desatualizado": False}]
    for e in ETAPAS[1:]:
        if e == "imagens":
            out.append({"etapa": e, "nome": t(e), "feito": n_imagens > 0, "desatualizado": False, "quantidade": n_imagens})
            continue
        if e == "dossier":
            out.append({"etapa": e, "nome": t(e), "feito": bool(fio.get("dossier_em")), "desatualizado":
                        bool(fio.get("dossier_em")) and fio.get("dossier_geometria") != geometria})
            continue
        lig = ult.get(e)
        feito = bool(lig) or (e == "dce" and tem_dce)
        des = bool(lig) and lig.get("geometria") != geometria
        item = {"etapa": e, "nome": t(e), "feito": feito, "desatualizado": des}
        if lig:
            item.update({"ref": lig.get("valor"), "campo": lig.get("campo"), "em": lig.get("em")})
        if des:
            item["aviso"] = t("desatualizado")
        out.append(item)
    return out


async def estado(db, user: Dict[str, Any], pid: str) -> Dict[str, Any]:
    p, m, der = await carregar(user, pid)
    r = resumo(p, m, der)
    fio = await db[COL].find_one({"projet_id": pid, "user_id": user["user_id"]}, {"_id": 0}) or {}
    imgs = await listar_imagens(db, user, pid, verificar=False)
    etapas = _etapas(fio, r["geometria"], len(imgs), bool(p.get("dce_id")))
    return {"projeto": r, "ligacoes": fio.get("ligacoes") or [], "imagens": imgs, "etapas": etapas,
            "proxima_etapa": next((e["etapa"] for e in etapas if not e["feito"] or e["desatualizado"]), None)}


async def ligar(db, user: Dict[str, Any], pid: str, campo: str, valor: str, nota: str = "") -> Dict[str, Any]:
    if campo not in LIGACOES:
        raise ErroFio(422, t("campo"))
    valor = (str(valor or "")).strip()
    if not valor or len(valor) > 120:
        raise ErroFio(422, t("valor"))
    _, m, _ = await carregar(user, pid)
    lig = {"campo": campo, "valor": valor, "geometria": impressao_geometria(m), "em": _agora(), "nota": (nota or "")[:300]}
    flt = {"projet_id": pid, "user_id": user["user_id"]}
    if LIGACOES[campo]:
        await db[COL].update_one(flt, {"$pull": {"ligacoes": {"campo": campo, "valor": valor}}})
    else:
        await db[COL].update_one(flt, {"$pull": {"ligacoes": {"campo": campo}}})
    await db[COL].update_one(flt, {"$push": {"ligacoes": lig}, "$set": {"atualizado_em": lig["em"]},
                                   "$setOnInsert": {"criado_em": lig["em"]}}, upsert=True)
    return lig


# ------------------------------------------------------------------------------- imagens (BIM, renders, fotos)
def tipo_mime(data: bytes) -> Optional[str]:
    for magia, mime in MIMES.items():
        if data[:len(magia)] == magia:
            if mime == "image/webp" and data[8:12] != b"WEBP":
                return None
            return mime
    return None


async def adicionar_imagem(db, user: Dict[str, Any], pid: str, data: bytes, tipo: str = "outra", legenda: str = "") -> Dict[str, Any]:
    mime = tipo_mime(data or b"")
    if not mime:
        raise ErroFio(415, t("img_tipo"))
    if len(data) > MAX_BYTES:
        raise ErroFio(413, t("img_grande"))
    _, m, _ = await carregar(user, pid)
    flt = {"projet_id": pid, "user_id": user["user_id"]}
    if await db[COL_IMG].count_documents(flt) >= MAX_IMAGENS:
        raise ErroFio(409, t("img_max"))
    doc = {"imagem_id": "img_" + secrets.token_hex(6), **flt, "tipo": tipo if tipo in TIPOS_IMAGEM else "outra",
           "legenda": (legenda or "").strip()[:200], "mime": mime, "bytes": len(data), "data": data,
           "sha256": hashlib.sha256(data).hexdigest(), "geometria": impressao_geometria(m), "criado_em": _agora()}
    dup = await db[COL_IMG].find_one({**flt, "sha256": doc["sha256"]}, {"_id": 0, "data": 0})
    if dup:
        return dup                                              # a mesma imagem não entra duas vezes
    await db[COL_IMG].insert_one(dict(doc))
    doc.pop("data")
    return doc


async def listar_imagens(db, user: Dict[str, Any], pid: str, verificar: bool = True) -> List[Dict[str, Any]]:
    if verificar:
        await carregar(user, pid)
    cur = db[COL_IMG].find({"projet_id": pid, "user_id": user["user_id"]}, {"_id": 0, "data": 0})
    out = [d async for d in cur]
    out.sort(key=lambda d: d.get("criado_em") or "")
    return out


async def ler_imagem(db, user: Dict[str, Any], pid: str, iid: str) -> Dict[str, Any]:
    d = await db[COL_IMG].find_one({"projet_id": pid, "user_id": user["user_id"], "imagem_id": iid}, {"_id": 0})
    if not d:
        raise ErroFio(404, t("img_nao"))
    return d


async def apagar_imagem(db, user: Dict[str, Any], pid: str, iid: str) -> bool:
    r = await db[COL_IMG].delete_one({"projet_id": pid, "user_id": user["user_id"], "imagem_id": iid})
    if not getattr(r, "deleted_count", 0):
        raise ErroFio(404, t("img_nao"))
    return True


# ------------------------------------------------------------------------------- dossier final
async def _pranchas(user: Dict[str, Any], pid: str) -> Optional[bytes]:
    """As peças desenhadas oficiais do projeto: a mesma rota que o botão «Planches PDF» do Ateliê."""
    AA = _aa()
    for r in getattr(AA.router, "routes", []):
        if str(getattr(r, "path", "")).endswith("/projets/{pid}/pranchas.pdf") and "GET" in (getattr(r, "methods", None) or ()):
            try:
                resp = await r.endpoint(pid=pid, user=user)
                body = getattr(resp, "body", None)
                return bytes(body) if body and bytes(body[:4]) == b"%PDF" else None
            except Exception:  # noqa: BLE001 — o dossier sai na mesma, com o aviso
                return None
    return None


async def dossier(db, user: Dict[str, Any], pid: str) -> Tuple[bytes, Dict[str, Any]]:
    est = await estado(db, user, pid)
    imgs = []
    for meta in est["imagens"]:
        try:
            imgs.append({**meta, "data": (await ler_imagem(db, user, pid, meta["imagem_id"]))["data"]})
        except ErroFio:
            continue
    pr = await _pranchas(user, pid)
    pdf = montar_pdf(est, imgs, pr)
    geo = est["projeto"]["geometria"]
    await db[COL].update_one({"projet_id": pid, "user_id": user["user_id"]},
                             {"$set": {"dossier_em": _agora(), "dossier_geometria": geo},
                              "$setOnInsert": {"criado_em": _agora(), "ligacoes": []}}, upsert=True)
    return pdf, est


def _fmt(v: Any, nd: int = 2) -> str:
    if isinstance(v, (int, float)):
        s = f"{v:,.{nd}f}".replace(",", " ")
        return s.replace(".", ",") if LANG in ("pt", "fr") else s
    return "" if v is None else str(v)


def montar_pdf(est: Dict[str, Any], imagens: List[Dict[str, Any]], pranchas: Optional[bytes]) -> bytes:
    import fitz  # PyMuPDF

    W, H, M = 595, 842, 48
    doc = fitz.open()
    pr = est["projeto"]
    estado_txt = {"y": H}
    pagina = {"p": None}

    def nova():
        pagina["p"] = doc.new_page(width=W, height=H)
        estado_txt["y"] = M

    def linha(txt: str, tam: float = 10, negrito: bool = False, cor=(0, 0, 0), recuo: float = 0):
        larg = W - 2 * M - recuo
        n_car = max(20, int(larg / (tam * 0.5)))
        partes = []
        for bloco in str(txt).split("\n"):
            while len(bloco) > n_car:
                corte = bloco.rfind(" ", 0, n_car)
                corte = corte if corte > n_car // 2 else n_car
                partes.append(bloco[:corte])
                bloco = bloco[corte:].lstrip()
            partes.append(bloco)
        for parte in partes:
            if pagina["p"] is None or estado_txt["y"] + tam * 1.5 > H - M:
                nova()
            pagina["p"].insert_text((M + recuo, estado_txt["y"] + tam), parte, fontsize=tam,
                                    fontname="hebo" if negrito else "helv", color=cor)
            estado_txt["y"] += tam * 1.45

    def espaco(h: float = 8):
        estado_txt["y"] += h

    # capa
    nova()
    estado_txt["y"] = 200
    linha(t("titulo_dossier"), 26, True)
    espaco(10)
    linha(pr.get("titulo") or "", 18, True)
    for x in (pr.get("morada"), pr.get("dono_obra")):
        if x:
            linha(x, 12)
    espaco(30)
    linha(f"{t('gerado')} {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC", 9, cor=(0.35, 0.35, 0.35))
    linha(f"{t('impressao')} : {pr.get('geometria')}", 9, cor=(0.35, 0.35, 0.35))

    # seguimento
    nova()
    linha(t("etapas"), 15, True)
    espaco(4)
    for e in est["etapas"]:
        st = t("feito") if e["feito"] else t("por_fazer")
        cor = (0.75, 0.3, 0) if e.get("desatualizado") else ((0, 0.45, 0.2) if e["feito"] else (0.4, 0.4, 0.4))
        extra = f" — {e['ref']}" if e.get("ref") else ""
        linha(f"• {e['nome']} : {st}{extra}", 10, cor=cor)
        if e.get("desatualizado"):
            linha(f"   {t('desatualizado')}", 9, cor=(0.75, 0.3, 0))

    # áreas
    espaco(10)
    linha(t("areas"), 15, True)
    for q in pr.get("quadro_areas") or []:
        linha(f"{q.get('piso')} : {t('bruta')} {_fmt(q.get('area_bruta_m2'))} m² · {t('util')} {_fmt(q.get('area_util_m2'))} m²", 10)
    tot = pr.get("totais") or {}
    linha(f"{t('total')} : {t('bruta')} {_fmt(tot.get('area_bruta_construcao_m2'))} m² · {t('util')} {_fmt(tot.get('area_util_m2'))} m²", 10, True)

    # envolvente
    espaco(10)
    linha(t("envolvente"), 15, True)
    f = pr.get("fachada") or {}
    linha(t("fachada").format(b=_fmt(f.get("area_bruta_m2")), v=_fmt(f.get("area_vaos_m2")), l=_fmt(f.get("area_liquida_m2"))), 10)
    c = pr.get("cobertura") or {}
    linha(t("cobertura").format(t=str(c.get("tipo") or "").replace("_", " "), a=_fmt(c.get("area_m2")), i=_fmt(c.get("inclinacao_graus"), 0)), 10)
    espaco(6)
    linha(t("paredes"), 12, True)
    for w in pr.get("paredes_por_tipo") or []:
        linha(f"{w.get('nome')} ({t('ext') if w.get('exterior') else t('int')}) : {_fmt(w.get('comprimento_liquido_m'))} m · "
              f"{_fmt(w.get('area_liquida_m2'))} m²", 10, True)
        for cam in w.get("camadas") or []:
            linha(f"– {cam.get('material')} {_fmt((cam.get('esp_m') or 0) * 100, 1)} cm : {_fmt(cam.get('area_m2'))} m² · "
                  f"{_fmt(cam.get('volume_m3'), 3)} m³", 9, recuo=12)
    if pr.get("vaos"):
        espaco(6)
        linha(t("vaos"), 12, True)
        for v in pr["vaos"]:
            dims = " × ".join(_fmt(v.get(k)) for k in ("largura_m", "altura_m") if v.get(k) is not None)
            linha(f"{v.get('codigo')} · {v.get('tipo') or ''} {dims} m · {v.get('caixilharia') or ''} × {v.get('quantidade')}", 9, recuo=6)
    if pr.get("avisos"):
        espaco(6)
        linha(t("avisos"), 12, True)
        for a in pr["avisos"][:40]:
            linha(f"– {a.get('msg') if isinstance(a, dict) else a}", 9)
    espaco(10)
    linha(t("nota"), 8, cor=(0.35, 0.35, 0.35))

    # imagens
    for k, im in enumerate(imagens, 1):
        nova()
        leg = im.get("legenda") or f"{t('imagem')} {k}"
        linha(f"{leg}  ({im.get('tipo')})", 12, True)
        if im.get("geometria") and im.get("geometria") != pr.get("geometria"):
            linha(t("desatualizado"), 9, cor=(0.75, 0.3, 0))
        rect = fitz.Rect(M, estado_txt["y"] + 6, W - M, H - M)
        try:
            pagina["p"].insert_image(rect, stream=im["data"], keep_proportion=True)
        except Exception:  # noqa: BLE001 — imagem corrompida não impede o dossier
            linha("—", 10)

    # peças desenhadas
    if pranchas:
        try:
            src = fitz.open(stream=pranchas, filetype="pdf")
            doc.insert_pdf(src)
            src.close()
        except Exception:  # noqa: BLE001
            nova()
            linha(t("sem_pranchas"), 10)
    else:
        nova()
        linha(t("pranchas"), 15, True)
        linha(t("sem_pranchas"), 10)

    doc.set_metadata({"title": f"{t('titulo_dossier')} — {pr.get('titulo') or ''}", "creator": "ConstruPilot"})
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out
