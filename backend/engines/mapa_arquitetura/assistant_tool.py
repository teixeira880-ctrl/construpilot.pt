"""Ferramenta do Assistente : MAPA DE QUANTIDADES DE ARQUITETURA medido num desenho DWFX (camadas e escala do CAD).

medir_arquitetura_dwfx → lê as plantas e os alçados do DWFX, mede compartimentos, paredes, portas e vãos e devolve o resumo,
os pressupostos, as perguntas e dois ficheiros : o mapa em Excel (com fórmulas e a folha «Controlo» com as imagens do que foi
medido) e o PDF de controlo. Determinístico (sem IA)."""
from __future__ import annotations

import asyncio
import base64
import re
import hashlib
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from engines import mapa_controlo_xlsx

from . import dwfx, excel, medicao

log = logging.getLogger(__name__)
MAX_ARTIFACT = 25 * 1024 * 1024
MIME = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}

TOOLS = [
    {"type": "function", "name": "medir_arquitetura_dwfx", "strict": False,
     "description": (
         "MAPA DE QUANTIDADES DE ARQUITETURA a partir de um desenho DWFX (.dwfx exportado do AutoCAD, com camadas e escala do modelo). "
         "Mede diretamente no desenho, sem IA : compartimentos (área e perímetro por piso, nome pelo rótulo da planta), pavimento interior, "
         "instalações sanitárias, varandas, tetos, paredes de fachada e interiores (pares de linhas da camada de paredes), portas interiores "
         "(raio do arco) e vãos exteriores nos alçados (largura × altura). Devolve o resumo, pressupostos, perguntas e dois ficheiros : Excel com "
         "fórmulas e folha Controlo com as imagens do que foi medido, e PDF de controlo. Usar SEMPRE que pedem mapa de quantidades / medições de "
         "arquitetura e há um .dwfx anexado. Para a estrutura em PDF usar medir_planta_estrutural. Demora 5 a 60 s."),
     "parameters": {"type": "object", "properties": {
         "document_ids": {"type": "array", "items": {"type": "string"}, "description": "doc_… dos ficheiros .dwfx"},
         "pe_direito_m": {"type": "number", "description": "Só se o utilizador a indicar explicitamente : por defeito a altura de cada piso é lida automaticamente nas cotas de pavimento das plantas (piso a piso)."},
         "documentos_estrutura": {"type": "array", "items": {"type": "string"}, "description": "Opcional : doc_… dos PDF do projeto de ESTRUTURA anexados (o quadro de elementos de fundação entra no mapa : sapatas, betão, cofragem, betão de limpeza, aço)."},
         "mapa_camadas": {"type": "object", "description": "Opcional : {nome da camada: paredes|trama|fino|sanitarios|cozinha|muros} quando os nomes do gabinete não são reconhecidos."}},
         "required": ["document_ids"], "additionalProperties": False}},
]
TOOL_NAMES = {t["name"] for t in TOOLS}
TOOL_STATUS = {"medir_arquitetura_dwfx": "A medir o desenho de arquitetura (compartimentos, paredes, portas, vãos)…"}
INSTRUCTIONS = (
    "\n\nMAPA DE QUANTIDADES DE ARQUITETURA (medir_arquitetura_dwfx) : quando o utilizador anexa um .dwfx e pede o mapa de quantidades, as "
    "medições ou as áreas, chama medir_arquitetura_dwfx com os documentos, sem pedir nada antes. Nunca digas que não há motor para mapas de "
    "quantidades : há medir_arquitetura_dwfx (arquitetura em DWFX), medir_planta_estrutural (estrutura em PDF) e medir_camadas_cad (DWG/DXF). "
    "Se também houver PDF do projeto de estrutura anexado, passa-o em documentos_estrutura (sapatas do quadro de fundações entram no mapa). "
    "Depois : 1) apresenta o resumo tal como vem, sem recalcular nem completar com rácios ; 2) lista os pressupostos e faz as perguntas "
    "devolvidas ; 3) diz o que NÃO está incluído ; 4) os ficheiros aparecem como botões : convida a conferir o PDF / a folha Controlo do Excel, "
    "que mostram o que foi medido pintado sobre o desenho. A altura das paredes é lida automaticamente nas cotas das plantas : não a perguntes ; só se o utilizador indicar outra, volta a chamar com pe_direito_m. "
    "É uma medição a validar pelo projetista.")


def _now():
    return datetime.now(timezone.utc).isoformat()


def medir(docs: list, pe_direito=None, mapa_camadas=None, out_dir=None, estrutura: list | None = None) -> dict:
    """docs = [(nome, bytes .dwfx)] — mede o primeiro DWFX legível (um projeto por chamada)."""
    avisos = []
    for nome, data in docs:
        if not dwfx.e_dwfx(data):
            avisos.append(f"{nome} : não é um DWFX.")
            continue
        modelo = medicao.medir(data, pe_direito=pe_direito, mapa_camadas=mapa_camadas, nome_ficheiro=nome)
        modelo["avisos"] = avisos + modelo.get("avisos", [])
        if modelo.get("ok") and out_dir:
            out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
            titulo = Path(nome).stem[:60]
            from . import premium
            extras, nao = [], list(premium.NAO_MEDIDO_PADRAO)
            for nome_e, pdf in estrutura or []:
                try:
                    from engines.mapa_estrutura import fundacoes
                    pl = fundacoes.ler_planta(pdf)
                    if pl:
                        enterrado = min((p for p in modelo["pisos"] if (p.get("cota") or {}).get("valor")),
                                        key=lambda p: p["cota"]["valor"], default=None)
                        area_cave = (sum(c["area"] for c in enterrado["compartimentos"] if not c["exterior"])
                                     if enterrado and re.search(r"cave|sub|garag", enterrado["piso"], re.I) else None)
                        try:
                            from . import terreno as _ter
                            z_t = dwfx.abrir(data)
                            ter = _ter.ler(z_t, dwfx.folhas(z_t))
                        except Exception as exc:  # noqa: BLE001
                            ter = {}
                            modelo["avisos"].append(f"Levantamento topográfico não lido ({type(exc).__name__}) — escavação por medir.")
                        a_impl = ((enterrado or {}).get("envolvente") or {}).get("area") if area_cave else None
                        extras += fundacoes.linhas_planta(pl, origem=nome_e, area_laje_terrea=area_cave, terreno=ter, area_implantacao=a_impl)
                        nao = [x for x in nao if not x["designacao"].startswith(("Muros de suporte", "Escavação geral"))]
                    try:                              # lajes, vigas, aço base das lajes e aço dos muros (cortes tipo)
                        from engines.mapa_estrutura import lajes_dossier
                        mur = fundacoes.muros_por_nome(pl) if pl else None
                        est_l = lajes_dossier.linhas_mapa(pdf, nome_e, mur)
                        if est_l:
                            extras += est_l
                            nao = [x for x in nao if not x["designacao"].startswith(("Pilares, vigas, lajes", "Aço A500"))]
                            try:
                                from engines.mapa_estrutura import pilares
                                import pymupdf
                                est_p = pilares.linhas_mapa(pilares.ler(pymupdf.open(stream=pdf, filetype="pdf"),
                                                                        base_fundacao=(pl or {}).get("cota_sup_linear")), nome_e)
                            except Exception as exc:  # noqa: BLE001
                                est_p = []
                                modelo["avisos"].append(f"{nome_e} : quadro de pilares não lido ({type(exc).__name__}).")
                            if est_p:
                                extras += est_p
                            else:
                                nao.append({"capitulo": "Estrutura", "designacao": "Pilares — betão, cofragem e aço (quadro de pilares)",
                                            "descricao": "quadro de pilares do projeto de estrutura", "un": "m³"})
                            try:
                                est_r = lajes_dossier.reforcos(pdf, nome_e, {pl["pagina"]} if pl else None)
                            except Exception as exc:  # noqa: BLE001
                                est_r = []
                                modelo["avisos"].append(f"{nome_e} : armaduras desenhadas não lidas ({type(exc).__name__}).")
                            if est_r:
                                extras += est_r
                            else:
                                nao.append({"capitulo": "Estrutura", "designacao": "Reforços desenhados das lajes e armaduras das vigas",
                                            "descricao": "armaduras desenhadas nas plantas de laje", "un": "kg"})
                    except Exception as exc:  # noqa: BLE001
                        modelo["avisos"].append(f"{nome_e} : lajes não lidas ({type(exc).__name__}).")
                    q = fundacoes.ler_quadro(pdf)
                    if q:
                        extras += fundacoes.linhas_mapa(q, nome_e)
                        nao = [x for x in nao if x.get("_chave") != "sapatas"]
                        if q.get("recobrimento") is None:
                            modelo["avisos"].append(f"{nome_e} : recobrimento não lido nas notas — aço das sapatas por medir.")
                except Exception as exc:  # noqa: BLE001
                    modelo["avisos"].append(f"{nome_e} : quadro de fundações não lido ({type(exc).__name__}).")
            try:                                             # estrada de acesso, passeios, lancis, muros de vedação
                from . import exteriores
                z_ = dwfx.abrir(data)
                extras += exteriores.linhas_mapa(exteriores.medir(z_, dwfx.folhas(z_)))
            except Exception as exc:  # noqa: BLE001
                modelo["avisos"].append(f"Arranjos exteriores não lidos ({type(exc).__name__}).")
            xlsx = excel.gerar(modelo, str(out / "Mapa_quantidades.xlsx"), titulo)
            premium.gerar_xlsx(modelo, xlsx, titulo, extras=extras, nao_medido=nao)
            pags = premium.desenhos(modelo, titulo)                 # plantas, alçados e cortes com os elementos numerados
            mapa_controlo_xlsx.anexar_imagens(xlsx, pags, "Plantas, alçados e cortes com cada elemento numerado (W paredes, P portas, "
                                                          "C compartimentos, V vãos) : os números são os do mapa.")
            modelo["files"] = {"xlsx": xlsx, "controlo": premium.gerar_pdf(modelo, str(out / "Mapa_quantidades.pdf"), titulo,
                                                                           extras=extras, nao_medido=nao)}
        return modelo
    return {"ok": False, "avisos": avisos or ["Nenhum DWFX nos documentos."]}


async def _carregar(db, ids, uid) -> list:
    """Bytes originais dos anexos (o .dwfx não passa pela conversão para PDF do carregador genérico)."""
    docs = []
    for did in ids:
        d = await db.assistant_docs.find_one({"doc_id": did, "user_id": uid}, {"_id": 0, "filename": 1, "data_b64": 1, "chunk_count": 1})
        if not d:
            raise PermissionError(f"Documento {did} inacessível para esta conta")
        if d.get("data_b64"):
            data = base64.b64decode(d["data_b64"])
        elif d.get("chunk_count"):
            ch = [c async for c in db.assistant_doc_chunks.find({"doc_id": did, "user_id": uid}, {"_id": 0}).sort("index", 1)]
            if [c.get("index") for c in ch] != list(range(d["chunk_count"])):
                raise ValueError(f"{d.get('filename') or did} está incompleto no servidor : importe de novo.")
            data = b"".join(base64.b64decode(c["data_b64"]) for c in ch)
        else:
            raise ValueError(f"{d.get('filename') or did} está vazio no servidor.")
        docs.append((d.get("filename") or did, data))
    return docs


async def _store(db, uid, cid, request_id, kind, path: Path, title):
    fmt = "xlsx" if path.suffix == ".xlsx" else "pdf"
    data = path.read_bytes()
    if len(data) > MAX_ARTIFACT:
        raise ValueError(f"{path.name} : {len(data)} bytes")
    aid = "file_" + hashlib.sha256((request_id + kind + path.name).encode()).hexdigest()[:28]
    doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": request_id, "title": title, "body": "",
           "filename": f"ConstruPilot_{path.name}", "format": fmt, "kind": kind, "mime": MIME[fmt], "size": len(data),
           "data_b64": base64.b64encode(data).decode(), "source_artifact_ids": [], "created_at": _now(), "illustrative": False,
           "download": f"/assistant/artifacts/{aid}/content"}
    await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
    return {k: doc[k] for k in ("artifact_id", "title", "filename", "format", "kind", "mime", "size", "download")}


def _publico(m: dict) -> dict:
    return {"ok": True, "resumo": m["resumo"],
            "pisos": [{"piso": p["piso"], "compartimentos": len(p["compartimentos"]),
                       "area_interior": round(sum(c["area"] for c in p["compartimentos"] if not c["exterior"]), 2),
                       "portas_interiores": sum(1 for d in p["portas"] if d["tipo"] == "interior")} for p in m["pisos"]],
            "alcados": [{"vista": v["vista"], "vaos": len(v["vaos"]), "area": round(sum(d["L"] * d["H"] for d in v["vaos"]), 2)} for v in m["alcados"]],
            "pressupostos": m["pressupostos"], "perguntas": m["perguntas"], "avisos": m["avisos"][:20], "nao_incluido": m["nao_incluido"],
            "nota": "Medição determinística sobre o DWFX. Apresentar o resumo tal como está ; o Excel tem a folha Controlo com as imagens do que foi medido."}


async def execute(name: str, args: dict, user: dict, conv: dict, db, doc_loader=None) -> dict:
    uid, cid = user["user_id"], conv.get("conversation_id")
    ids = [d for d in args.get("document_ids") or [] if d]
    if not ids:
        return {"ok": False, "error": "Junte o desenho de arquitetura em .dwfx."}
    try:
        docs = await (doc_loader or _carregar)(db, ids, uid)
    except (PermissionError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    pd, mc = args.get("pe_direito_m") or None, args.get("mapa_camadas") or None
    est = []
    if args.get("documentos_estrutura"):
        try:
            est = [(n, d) for n, d in await _carregar(db, [x for x in args["documentos_estrutura"] if x], uid) if d[:4] == b"%PDF"]
        except (PermissionError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
    request_id = hashlib.sha256(("".join(ids) + str(pd) + str(mc) + str(args.get("documentos_estrutura"))).encode()).hexdigest()[:16]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            modelo = await asyncio.wait_for(asyncio.to_thread(medir, docs, pd, mc, tmp, est), 300)
            if not modelo.get("ok"):
                return {"ok": False, "error": " ".join(modelo.get("avisos") or ["Desenho não legível."]),
                        "o_que_falta": "DWFX exportado do AutoCAD (layouts com escala), com as camadas de paredes e os rótulos dos compartimentos."}
            arts = [await _store(db, uid, cid, request_id, "mapa_arquitetura_xlsx", Path(modelo["files"]["xlsx"]), "Mapa de quantidades (Excel)"),
                    await _store(db, uid, cid, request_id, "mapa_arquitetura_controlo", Path(modelo["files"]["controlo"]), "Mapa de quantidades premium com plantas numeradas (PDF)")]
    except asyncio.TimeoutError:
        return {"ok": False, "error": "A medição excedeu 5 minutos : envie só as folhas de plantas e alçados."}
    except Exception as exc:  # noqa: BLE001
        log.exception("medir_arquitetura_dwfx failed")
        return {"ok": False, "error": f"Medição impossível — {type(exc).__name__}: {str(exc)[:200]}"}
    return {**_publico(modelo), "artifacts": arts}
