"""Cópia local dos dados oficiais da DGT (CRUS do PDM, CAOP, servidões e restrições) — para quando o serviço está em baixo.

Cada consulta bem-sucedida guarda (1) os elementos devolvidos, com geometria, e (2) a «cobertura»: a caixa consultada e se a
resposta foi completa. Quando a DGT falha, responde-se a partir da cópia só se a caixa pedida estiver DENTRO de uma caixa já
consultada com resposta completa — só assim também a AUSÊNCIA de servidões é um dado fiável. Caso contrário devolve-se None
(serviço indisponível), como antes. Tudo o que sai da cópia vem marcado com a data da consulta original.

Persistência: um ficheiro JSON-lines por coleção em DGT_CACHE_DIR (por omissão backend/data/dgt_cache).
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from shapely.geometry import box, shape
except Exception:  # noqa: BLE001
    box = shape = None

VALIDADE_S = 180 * 24 * 3600          # 6 meses: as cartas do PDM e das servidões mudam pouco; a data fica sempre registada
MAX_ELEMENTOS = 4000                  # por coleção, em memória e em disco
_DIR = os.environ.get("DGT_CACHE_DIR") or os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "dgt_cache"))
_lock = threading.Lock()
_mem: Dict[str, Dict[str, Any]] = {}  # col -> {"cob": [(bbox, ts)], "els": {key: (geom, feature, ts)}, "carregado": bool}


def _bb(bbox: str) -> Tuple[float, float, float, float]:
    a = [float(x) for x in bbox.split(",")]
    return a[0], a[1], a[2], a[3]


def _contem(ext: Tuple[float, ...], inn: Tuple[float, ...]) -> bool:
    return ext[0] <= inn[0] and ext[1] <= inn[1] and ext[2] >= inn[2] and ext[3] >= inn[3]


def _ficheiro(col: str) -> str:
    return os.path.join(_DIR, "".join(c if c.isalnum() or c in "-_" else "_" for c in col) + ".jsonl")


def _carregar(col: str) -> Dict[str, Any]:
    c = _mem.get(col)
    if c is not None:
        return c
    c = {"cob": [], "els": {}}
    try:
        with open(_ficheiro(col), encoding="utf-8") as fh:
            for ln in fh:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if time.time() - r.get("ts", 0) > VALIDADE_S:
                    continue
                if r.get("t") == "cob":
                    c["cob"].append((tuple(r["bbox"]), r["ts"]))
                elif r.get("t") == "el" and shape is not None:
                    try:
                        c["els"][r["k"]] = (shape(r["f"]["geometry"]), r["f"], r["ts"])
                    except Exception:  # noqa: BLE001
                        pass
    except OSError:
        pass
    _mem[col] = c
    return c


def _escrever(col: str, linhas: List[dict]) -> None:
    try:
        os.makedirs(_DIR, exist_ok=True)
        with open(_ficheiro(col), "a", encoding="utf-8") as fh:
            for r in linhas:
                fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        pass   # disco só de leitura: fica a cópia em memória


def _chave(f: dict) -> str:
    fid = f.get("id")
    if fid not in (None, ""):
        return str(fid)
    return json.dumps(f.get("properties") or {}, sort_keys=True, ensure_ascii=False)[:300] + str(hash(json.dumps(f.get("geometry"))))


def guardar(col: str, bbox: str, feats: List[dict], completa: bool) -> None:
    """Regista o resultado de uma consulta bem-sucedida."""
    if shape is None:
        return
    ts = time.time()
    linhas = []
    if any(not f.get("geometry") for f in feats):
        completa = False      # sem geometria não se pode responder depois por localização: não conta como cobertura
    with _lock:
        c = _carregar(col)
        for f in feats:
            if not f.get("geometry"):
                continue
            k = _chave(f)
            try:
                g = shape(f["geometry"])
            except Exception:  # noqa: BLE001
                continue
            c["els"][k] = (g, f, ts)
            linhas.append({"t": "el", "k": k, "ts": ts, "f": {"id": f.get("id"), "geometry": f["geometry"],
                                                              "properties": f.get("properties")}})
        if completa:
            c["cob"].append((_bb(bbox), ts))
            linhas.append({"t": "cob", "bbox": list(_bb(bbox)), "ts": ts})
        if len(c["els"]) > MAX_ELEMENTOS:
            for k, _ in sorted(c["els"].items(), key=lambda kv: kv[1][2])[: len(c["els"]) - MAX_ELEMENTOS]:
                c["els"].pop(k, None)
        if len(c["cob"]) > MAX_ELEMENTOS:
            c["cob"] = c["cob"][-MAX_ELEMENTOS:]
    _escrever(col, linhas)


def consultar(col: str, bbox: str) -> Optional[Tuple[List[dict], float]]:
    """(elementos que intersetam a caixa, data da consulta original) — ou None se a cópia não cobre esta caixa."""
    if shape is None:
        return None
    with _lock:
        c = _carregar(col)
        bb = _bb(bbox)
        cob = [ts for ext, ts in c["cob"] if _contem(ext, bb)]
        if not cob:
            return None
        caixa = box(*bb)
        out = [dict(f, _copia_ts=ts) for g, f, ts in c["els"].values() if g.intersects(caixa)]
    return out, min(cob)


def guardar_colecoes(cols: List[Dict[str, str]]) -> None:
    _escrever("_colecoes", [{"t": "lista", "ts": time.time(), "cols": cols}])


def colecoes() -> List[Dict[str, str]]:
    ult = []
    try:
        with open(_ficheiro("_colecoes"), encoding="utf-8") as fh:
            for ln in fh:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if r.get("t") == "lista" and time.time() - r.get("ts", 0) <= VALIDADE_S:
                    ult = r.get("cols") or ult
    except OSError:
        pass
    return ult


def data_txt(ts: float) -> str:
    return time.strftime("%d/%m/%Y", time.localtime(ts))


def usar_pasta(pasta: str) -> None:
    """Testes: muda a pasta da cópia e esquece a memória."""
    global _DIR
    with _lock:
        _DIR = pasta
        _mem.clear()
