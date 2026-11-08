"""Dados do local a partir da morada — fontes oficiais e abertas, com repli automático.

Cada função devolve {"ok": bool, "data": ..., "fonte": str, "url": str | None, "nota": str | None} e nunca levanta exceção:
um serviço em baixo produz ok=False e o piloto automático passa a uma hipótese prudente, registada como tal.

Fontes (por ordem):
- Geocodificação: Google Geocoding (se GOOGLE_MAPS_API_KEY) → Nominatim (livre, estruturada, sem número) → Photon →
  rua no concelho → localidade (marcada como «localidade», com pedido de confirmação no mapa).
- Município / freguesia: DGT OGC API «municipios» (CAOP) → campos da geocodificação.
- Classe de espaço do PDM: DGT OGC API «crus» (Carta do Regime de Uso do Solo).
- Servidões e restrições (REN, RAN, domínio hídrico…): coleções SRUP da DGT, descobertas dinamicamente.
- Cadastro predial (onde existe): coleção «cadastro» da DGT, descoberta dinamicamente.
- Altimetria: Google Elevation API (se chave) → EU-DEM 25 m (OpenTopoData). É o equivalente programático do Google Earth;
  NÃO substitui o levantamento topográfico georreferenciado exigido para o projeto (feito por topógrafo).
- Via de acesso: OpenStreetMap (Overpass), para orientar a frente do terreno.
- Ortofotomapa: DGT OGC API Maps «ortos-rgb» (30 cm) → Google Static Maps (satélite, se chave).
"""
from __future__ import annotations

import asyncio
import math
import os
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx

from . import dgt_cache as CACHE

UA = {"User-Agent": "ConstruPilot/1.0 (licenciamento automatico; info@construpilot.pt)"}
DGT = "https://ogcapi.dgterritorio.gov.pt"
NOMINATIM = "https://nominatim.openstreetmap.org"
PHOTON = "https://photon.komoot.io/api/"
OVERPASS = "https://overpass-api.de/api/interpreter"
OVERPASS_ESPELHOS = (OVERPASS, "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter")
OPENTOPO = "https://api.opentopodata.org/v1/eudem25m"
GMAPS = "https://maps.googleapis.com/maps/api"
TIMEOUT = httpx.Timeout(20.0, connect=8.0)

# Transporte injetável (testes): async (method, url, params, headers, want) -> (status, json | bytes | None)
Fetch = Callable[[str, str, Optional[dict], Optional[dict], str], Awaitable[Tuple[int, Any]]]


async def _http(method: str, url: str, params: Optional[dict] = None, headers: Optional[dict] = None,
                want: str = "json") -> Tuple[int, Any]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=UA, follow_redirects=True) as c:
            r = await c.request(method, url, params=params, headers=headers)
            if r.status_code >= 400:
                return r.status_code, None
            if want == "bytes":
                return r.status_code, r.content
            return r.status_code, r.json()
    except Exception:  # noqa: BLE001 — rede, JSON inválido, timeout: tratado como serviço indisponível
        return 0, None


_fetch: Fetch = _http
_SEMS: Dict[str, asyncio.Semaphore] = {}


async def _get(url: str, params: Optional[dict] = None, want: str = "json", tries: int = 3, conc: int = 4) -> Tuple[int, Any]:
    """GET com repetição (rede, 429, 5xx) e limite de pedidos simultâneos por serviço — os serviços públicos (DGT,
    OpenStreetMap) recusam rajadas; sem isto, uma consulta falhada passaria por «sem dados» (ex.: CRUS ou REN em falta)."""
    host = url.split("/")[2] if "//" in url else url
    dgt = "dgterritorio" in host and _fetch is _http
    if dgt:   # a DGT responde 503 (limite de pedidos do nginx) a rajadas: menos pedidos simultâneos e mais paciência
        conc, tries = min(conc, 2), max(tries, 5)
    loop_id = id(asyncio.get_running_loop())
    key = f"{host}:{loop_id}"
    sem = _SEMS.get(key)
    if sem is None:
        if len(_SEMS) > 50:
            _SEMS.clear()
        sem = _SEMS[key] = asyncio.Semaphore(conc)
    st, js = 0, None
    esperas = (1.5, 3.0, 5.0, 8.0) if dgt else (1.0, 2.5, 4.0)
    for i in range(max(1, tries)):
        async with sem:
            st, js = await _fetch("GET", url, params, None, want)
        if js is not None or st in (400, 401, 403, 404):
            return st, js
        if i < tries - 1:
            await asyncio.sleep(esperas[min(i, len(esperas) - 1)])
    return st, js


def set_transport(fn: Optional[Fetch]) -> None:
    """Substitui o transporte HTTP (testes). None repõe o real."""
    global _fetch
    _fetch = fn or _http


def _gkey() -> str:
    return (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()


def _res(ok: bool, data: Any = None, fonte: str = "", url: Optional[str] = None, nota: Optional[str] = None) -> Dict[str, Any]:
    return {"ok": ok, "data": data, "fonte": fonte, "url": url, "nota": nota}


def _tiny_bbox(lat: float, lon: float, d: float = 0.00002) -> str:
    return f"{lon - d},{lat - d},{lon + d},{lat + d}"


def _bbox_around(lat: float, lon: float, meters: float) -> str:
    dlat = meters / 111_320.0
    dlon = meters / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    return f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}"


# ------------------------------------------------------------------ geocodificação
def _limpa_morada(m: str) -> str:
    m = re.sub(r"\s+", " ", m or "").strip(" ,.")
    m = re.sub(r"\bn\.?\s*[º°]\s*|\bn\.?\s*o\.?\s*(?=\d)|\bn\.\s*(?=\d)", "", m, flags=re.I)   # «nº 7» → «7» (não toca em «Nova»)
    m = re.sub(r"\bmunic[ií]pio de\b", "", m, flags=re.I)
    return re.sub(r"\s*,\s*,", ",", m).strip(" ,")


async def geocode(morada: str) -> Dict[str, Any]:
    q = _limpa_morada(morada)
    if not q:
        return _res(False, nota="morada vazia")
    key = _gkey()
    if key:
        st, js = await _fetch("GET", f"{GMAPS}/geocode/json", {"address": q, "region": "pt", "language": "pt-PT", "key": key}, None, "json")
        if js and js.get("status") == "OK" and js.get("results"):
            r = js["results"][0]
            loc = r["geometry"]["location"]
            comp = {t: c["long_name"] for c in r.get("address_components", []) for t in c.get("types", [])}
            precisa = r["geometry"].get("location_type") in ("ROOFTOP", "RANGE_INTERPOLATED")
            return _res(True, {"lat": loc["lat"], "lon": loc["lng"], "morada_formatada": r.get("formatted_address", q),
                               "rua": comp.get("route"), "numero": comp.get("street_number"),
                               "freguesia": comp.get("administrative_area_level_3") or comp.get("locality"),
                               "concelho": comp.get("administrative_area_level_2"), "codigo_postal": comp.get("postal_code"),
                               "precisao": "porta" if precisa and comp.get("street_number") else "rua",
                               "consulta": q}, "Google Geocoding", None)
    diag: List[str] = []
    partes = [x.strip() for x in q.split(",") if x.strip()]
    rua_num = partes[0] if partes else q
    sem_num = re.sub(r"\b\d+[A-Za-z]?\b", "", q).replace(" ,", ",").strip(" ,")
    lugar = [x for x in partes[1:] if not re.match(r"^\d{4}(-\d{3})?\b", x)]      # freguesia / concelho
    concelho = lugar[-1] if lugar else ""
    freguesia = lugar[0] if len(lugar) >= 2 else ""
    cp = re.search(r"\b\d{4}-\d{3}\b", q)

    rua_pedida = _norm(re.sub(r"\b\d+[A-Za-z]?\b", "", rua_num)).strip(" ,") if partes and len(partes) > 1 else ""

    def _mesma_rua(rua: Optional[str]) -> bool:
        """A rua devolvida tem de ser a pedida (o Photon devolve por vezes uma rua vizinha: «Rua do Marco» por «Rua do Monte»)."""
        if not rua_pedida or not rua:
            return True
        from difflib import SequenceMatcher
        a, b = _norm(rua), rua_pedida
        return a == b or SequenceMatcher(None, a, b).ratio() >= 0.9

    def _match(texto: str) -> int:
        """Pontuação: o resultado tem de estar no concelho/freguesia pedidos (há muitas «Rua do Monte»)."""
        t = _norm(texto)
        sc = 0
        if concelho and _norm(concelho) in t:
            sc += 2
        if freguesia and _norm(freguesia) in t:
            sc += 3
        if cp and cp.group(0) in texto:
            sc += 3
        return sc

    def _nom(r: dict, consulta: str) -> Dict[str, Any]:
        a = r.get("address") or {}
        return {"lat": float(r["lat"]), "lon": float(r["lon"]), "morada_formatada": r.get("display_name", consulta),
                "rua": a.get("road"), "numero": a.get("house_number"),
                "freguesia": a.get("village") or a.get("suburb") or a.get("town") or a.get("city_district"),
                "concelho": a.get("municipality") or a.get("city") or a.get("county"),
                "codigo_postal": a.get("postcode"),
                "precisao": "porta" if a.get("house_number") else ("rua" if a.get("road") else "localidade"),
                "consulta": consulta,
                "via_geom": (r.get("geojson") if r.get("category", r.get("class")) == "highway"
                             and (r.get("geojson") or {}).get("type") in ("LineString", "MultiLineString") else None)}

    def _melhor(cands: List[Tuple[Dict[str, Any], str]], exige_rua: bool) -> Optional[Dict[str, Any]]:
        bons = [(d, txt) for d, txt in cands if (not exige_rua or d.get("rua")) and (not d.get("rua") or _mesma_rua(d["rua"]))]
        if not bons:
            return None
        # com freguesia indicada, uma rua tem de estar NESSA freguesia (há várias «Rua do Monte» no mesmo concelho)
        def minimo(d):
            return 5 if (freguesia and d.get("rua")) else (2 if concelho else 0)
        bons = [c for c in bons if _match(c[1]) >= minimo(c[0])]
        bons.sort(key=lambda c: (-_match(c[1]), {"porta": 0, "rua": 1, "localidade": 2}[c[0]["precisao"]]))
        return bons[0][0] if bons else None

    async def nominatim(params: dict, rotulo: str, exige_rua: bool = True):
        base = {"format": "jsonv2", "addressdetails": 1, "limit": 8, "countrycodes": "pt", "accept-language": "pt-PT",
                "polygon_geojson": 1, "polygon_threshold": 0.00002}
        st, js = await _fetch("GET", f"{NOMINATIM}/search", {**base, **params}, None, "json")
        diag.append(f"nominatim[{rotulo}]={st}:{len(js) if isinstance(js, list) else '-'}")
        await asyncio.sleep(1.05)   # política de uso do Nominatim: ≤ 1 pedido/s
        if not isinstance(js, list) or not js:
            return None
        return _melhor([(_nom(r, rotulo), r.get("display_name", "")) for r in js if r.get("lat")], exige_rua)

    async def photon(consulta: str, exige_rua: bool = True):
        st, js = await _fetch("GET", PHOTON, {"q": consulta, "limit": 8, "lang": "default", "bbox": "-9.6,36.9,-6.1,42.2"},
                              None, "json")
        feats = (js or {}).get("features") if isinstance(js, dict) else None
        diag.append(f"photon={st}:{len(feats) if feats is not None else '-'}")
        if not feats:
            return None
        cands = []
        for f in feats:
            pr, co = f.get("properties") or {}, (f.get("geometry") or {}).get("coordinates") or []
            if len(co) != 2 or (pr.get("countrycode") or "PT").upper() != "PT":
                continue
            rua = pr.get("street") or (pr.get("name") if pr.get("osm_key") == "highway" else None)
            d = {"lat": float(co[1]), "lon": float(co[0]),
                 "morada_formatada": ", ".join(x for x in (rua, pr.get("housenumber"), pr.get("district") or pr.get("locality"),
                                                           pr.get("city"), pr.get("postcode")) if x),
                 "rua": rua, "numero": pr.get("housenumber"), "freguesia": pr.get("district") or pr.get("locality"),
                 "concelho": pr.get("city") or pr.get("county"), "codigo_postal": pr.get("postcode"),
                 "precisao": "porta" if pr.get("housenumber") else ("rua" if rua else "localidade"), "consulta": consulta}
            cands.append((d, " ".join(str(v) for v in pr.values() if isinstance(v, str))))
        return _melhor(cands, exige_rua)

    def ok(d, fonte, url):
        return _res(True, d, fonte, url, "; ".join(diag) or None)

    # 1) morada completa  2) pesquisa estruturada  3) sem número  4) Photon  5) rua no concelho  6) só a localidade
    d = await nominatim({"q": q}, q, exige_rua=False)
    if d and d["precisao"] != "localidade":
        return ok(d, "OpenStreetMap (Nominatim)", f"{NOMINATIM}/search?q={q}")
    if concelho and rua_num:
        d = await nominatim({"street": rua_num, "city": concelho, "country": "Portugal"}, f"{rua_num}, {concelho}")
        if d:
            return ok(d, "OpenStreetMap (Nominatim)", f"{NOMINATIM}/search?street={rua_num}&city={concelho}")
    if sem_num != q:
        d = await nominatim({"q": sem_num}, sem_num)
        if d:
            return ok(d, "OpenStreetMap (Nominatim)", f"{NOMINATIM}/search?q={sem_num}")
    for consulta in dict.fromkeys([q, sem_num]):
        d = await photon(consulta)
        if d:
            return ok(d, "OpenStreetMap (Photon)", f"{PHOTON}?q={consulta}")
    if freguesia and concelho:
        # rua com nome único no concelho (todos os troços a < 500 m): aceita-se mesmo que a freguesia indicada não coincida
        # com a do OpenStreetMap (uniões de freguesias, nomes antigos) — fica registado para confirmação
        rua = re.sub(r"\b\d+[A-Za-z]?\b", "", rua_num).strip()
        base = {"format": "jsonv2", "addressdetails": 1, "limit": 10, "countrycodes": "pt", "accept-language": "pt-PT",
                "polygon_geojson": 1, "polygon_threshold": 0.00002}
        st, js = await _fetch("GET", f"{NOMINATIM}/search", {**base, "q": f"{rua}, {concelho}"}, None, "json")
        diag.append(f"nominatim[{rua}, {concelho}]={st}:{len(js) if isinstance(js, list) else '-'}")
        await asyncio.sleep(1.05)
        cands = [_nom(r, f"{rua}, {concelho}") for r in (js or []) if isinstance(js, list) and r.get("lat")
                 and _norm(concelho) in _norm(r.get("display_name", ""))]
        cands = [d for d in cands if d.get("rua") and _mesma_rua(d["rua"])]
        if cands:
            em_freg = [d for d in cands if _norm(freguesia) in _norm(d["morada_formatada"])]
            if em_freg:
                return ok(em_freg[0], "OpenStreetMap (Nominatim)", f"{NOMINATIM}/search?q={rua}, {concelho}")
            # o OSM diverge da freguesia indicada (uniões de freguesias, nomes antigos): decide a CAOP oficial da DGT
            frs = {}
            for d in cands[:3]:
                fr = frs[id(d)] = await freguesia_caop(d["lat"], d["lon"])
                if fr and _norm(freguesia) in _norm(fr):
                    d = dict(d, freguesia=fr, freguesia_divergente=freguesia, freguesia_motivo="caop")
                    return ok(d, "OpenStreetMap (Nominatim) + DGT CAOP", f"{NOMINATIM}/search?q={rua}, {concelho}")
            # nome indicado de uma freguesia VIZINHA (erro frequente nas cidades): aceita-se só se a rua for única no
            # concelho (todos os troços a < 500 m) e ficar a menos de 3 km do centro da freguesia indicada
            k = 111_320.0

            def dist(a_lat, a_lon, b_lat, b_lon):
                return math.hypot((a_lat - b_lat) * k, (a_lon - b_lon) * k * math.cos(math.radians(a_lat)))
            unica = all(dist(d["lat"], d["lon"], cands[0]["lat"], cands[0]["lon"]) < 500 for d in cands)
            if unica:
                st, jf = await _fetch("GET", f"{NOMINATIM}/search", {"q": f"{freguesia}, {concelho}", "format": "jsonv2",
                                                                    "limit": 1, "countrycodes": "pt"}, None, "json")
                diag.append(f"nominatim[{freguesia}, {concelho}]={st}")
                await asyncio.sleep(1.05)
                if isinstance(jf, list) and jf:
                    dk = dist(cands[0]["lat"], cands[0]["lon"], float(jf[0]["lat"]), float(jf[0]["lon"]))
                    if dk < 3000:
                        d = dict(cands[0], freguesia=frs.get(id(cands[0])) or cands[0].get("freguesia"),
                                 freguesia_divergente=freguesia, freguesia_motivo="vizinha", distancia_freguesia_m=round(dk))
                        return ok(d, "OpenStreetMap (Nominatim)", f"{NOMINATIM}/search?q={rua}, {concelho}")
    if lugar:
        loc = ", ".join(lugar)
        d = await nominatim({"q": loc}, loc, exige_rua=False) or await photon(loc, exige_rua=False)
        if d:
            d["precisao"] = "localidade"
            return ok(d, "OpenStreetMap", f"{NOMINATIM}/search?q={loc}")
    rede = any(x.split("=")[1].startswith(("0:", "403", "429", "5")) for x in diag)
    return _res(False, nota=("serviços de geocodificação inacessíveis: " if rede else "morada não encontrada: ") + "; ".join(diag))


def _norm(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if not unicodedata.combining(c)))


# ------------------------------------------------------------------ DGT OGC API
_COLLECTIONS: Dict[str, Any] = {"t": 0.0, "list": []}


async def dgt_collections() -> List[Dict[str, str]]:
    if _COLLECTIONS["list"] and time.time() - _COLLECTIONS["t"] < 6 * 3600:
        return _COLLECTIONS["list"]
    st, js = await _get(f"{DGT}/collections", {"f": "json"})
    cols = [{"id": c.get("id", ""), "title": c.get("title", "")} for c in (js or {}).get("collections", []) if c.get("id")]
    if cols:
        _COLLECTIONS.update(t=time.time(), list=cols)
        if _cache_ativa():
            CACHE.guardar_colecoes(cols)
        return cols
    return CACHE.colecoes() if _cache_ativa() else []


async def _dgt_items(col: str, bbox: str, limit: int = 20, uso: Optional[Dict[str, float]] = None) -> Optional[List[dict]]:
    """Elementos da coleção na caixa. Com a DGT em baixo, responde a cópia local se cobrir a caixa (registado em `uso`)."""
    st, js = await _get(f"{DGT}/collections/{col}/items", {"f": "json", "bbox": bbox, "limit": limit})
    if js is not None:
        feats = js.get("features") or []
        n_tot = js.get("numberMatched")
        completa = (len(feats) < limit) if not isinstance(n_tot, int) else n_tot <= len(feats)
        if _cache_ativa():
            CACHE.guardar(col, bbox, feats, completa)
        return feats
    hit = CACHE.consultar(col, bbox) if _cache_ativa() else None
    if hit is None:
        return None
    feats, ts = hit
    if uso is not None:
        uso[col] = ts
    return feats


_CACHE_EM_TESTE = {"on": False}


def _cache_ativa() -> bool:
    """A cópia local só é usada com o transporte HTTP real (ou num teste que a ligue explicitamente)."""
    return _fetch is _http or _CACHE_EM_TESTE["on"]


def _fonte_copia(fonte: str, ts: Optional[float]) -> str:
    return fonte if not ts else f"{fonte} — cópia local de {CACHE.data_txt(ts)} (serviço da DGT indisponível)"


async def prefetch_zona(lat: float, lon: float, raio_m: float = 600.0) -> Dict[str, int]:
    """Guarda na cópia local a classe do PDM, a CAOP e as servidões de uma zona (corre quando a DGT está a responder)."""
    bbox = _bbox_around(lat, lon, raio_m)
    cols = [c["id"] for c in await dgt_collections() if c["id"] in ("crus", "freguesias", "municipios")
            or _SRUP_PAT.search(c["id"].replace("_", " ") + " " + c["title"])]
    out = {}
    for col in cols[:40]:
        f = await _dgt_items(col, bbox, 500)
        out[col] = -1 if f is None else len(f)
    return out


def _props_text(p: dict) -> Dict[str, str]:
    return {str(k): str(v) for k, v in (p or {}).items() if isinstance(v, (str, int, float)) and str(v).strip()}


def _pick(p: Dict[str, str], *names: str) -> Optional[str]:
    low = {k.lower(): v for k, v in p.items()}
    for n in names:
        for k, v in low.items():
            if k == n or k.startswith(n):
                return v
    return None


async def municipio(lat: float, lon: float) -> Dict[str, Any]:
    uso: Dict[str, float] = {}
    feats = await _dgt_items("municipios", _tiny_bbox(lat, lon), 3, uso)
    if feats:
        p = _props_text(feats[0].get("properties"))
        nome = _pick(p, "municipio", "concelho", "nome", "designacao", "name")
        return _res(True, {"concelho": nome, "distrito": _pick(p, "distrito"), "props": p, "copia_local": uso.get("municipios")},
                    _fonte_copia("DGT — CAOP (municípios)", uso.get("municipios")), f"{DGT}/collections/municipios")
    return _res(False, nota="CAOP indisponível")


async def freguesia_caop(lat: float, lon: float) -> Optional[str]:
    """Nome oficial da freguesia (CAOP, DGT) no ponto, ou None se o serviço não responder."""
    feats = await _dgt_items("freguesias", _tiny_bbox(lat, lon), 2, {})
    if not feats:
        return None
    p = _props_text(feats[0].get("properties"))
    return _pick(p, "freguesia", "nome", "designacao", "name")


def classificar_solo(p: Dict[str, str]) -> Dict[str, Any]:
    """A partir dos atributos CRUS: solo urbano / rústico e categoria (texto)."""
    txt = " ".join(p.values()).lower()
    classe = _pick(p, "classe", "class", "cl_") or ""
    cat = _pick(p, "categoria", "subcategoria", "designacao", "desig", "uso") or ""
    tl = (classe + " " + txt).lower()
    if "rústico" in tl or "rustico" in tl or "rural" in tl:
        solo = "rustico"
    elif "urbano" in tl or "urbaniz" in tl:
        solo = "urbano"
    else:
        solo = "desconhecido"
    habit = any(w in txt for w in ("habitac", "residencia", "central", "urbaniza", "baixa densidade", "media densidade", "média densidade",
                                  "aglomerado", "edificaç", "edificac"))
    return {"solo": solo, "classe": classe or None, "categoria": cat or None, "habitacional": habit, "atributos": p}


async def crus(lat: float, lon: float) -> Dict[str, Any]:
    uso: Dict[str, float] = {}
    feats = await _dgt_items("crus", _tiny_bbox(lat, lon), 5, uso)
    if feats is None:
        return _res(False, nota="CRUS indisponível")
    if not feats:
        return _res(False, nota="sem polígono CRUS neste ponto")
    c = classificar_solo(_props_text(feats[0].get("properties")))
    c["copia_local"] = uso.get("crus")
    return _res(True, c, _fonte_copia("DGT — Carta do Regime de Uso do Solo (PDM)", uso.get("crus")), f"{DGT}/collections/crus")


_SRUP_PAT = re.compile(r"(\bren\b|reserva ecol|\bran\b|reserva agr|dom[ií]nio h[ií]dric|leito|cheia|patrim|monument|"
                       r"rede natura|zec|zpe|ardid|perigosidade|linha.{0,6}el[eé]tric|gasod|ferrov|estrad|aeroport)", re.I)


async def servidoes(lat: float, lon: float, raio_m: float = 40.0) -> Dict[str, Any]:
    cols = [c for c in await dgt_collections() if _SRUP_PAT.search(c["id"].replace("_", " ") + " " + c["title"])]
    if not cols:
        return _res(False, nota="lista de servidões indisponível")
    bbox = _bbox_around(lat, lon, raio_m)
    sem = asyncio.Semaphore(3)

    uso: Dict[str, float] = {}

    async def one(c):
        async with sem:
            f = await _dgt_items(c["id"], bbox, 3, uso)
            return c, f

    hits, falhadas = [], []
    for c, f in await asyncio.gather(*(one(c) for c in cols[:40])):
        if f is None:
            falhadas.append(c)
        elif f:
            hits.append({"id": c["id"], "titulo": c["title"]})
    ainda = []
    for c in falhadas:                     # segunda volta, uma a uma
        f = await _dgt_items(c["id"], bbox, 3, uso)
        if f is None:
            ainda.append({"id": c["id"], "titulo": c["title"]})
        elif f:
            hits.append({"id": c["id"], "titulo": c["title"]})
    ts = min(uso.values()) if uso else None
    return _res(True, {"afetado_por": hits, "consultadas": min(len(cols), 40), "falhas": len(ainda), "nao_consultadas": ainda,
                       "incompleta": bool(ainda), "raio_m": raio_m, "copia_local": ts,
                       "colecoes_da_copia": sorted(uso)},
                _fonte_copia("DGT — servidões e restrições de utilidade pública (SRUP)", ts), f"{DGT}/collections")


async def cadastro(lat: float, lon: float) -> Dict[str, Any]:
    cols = [c for c in await dgt_collections() if "cadastr" in (c["id"] + " " + c["title"]).lower()]
    for c in cols[:4]:
        feats = await _dgt_items(c["id"], _tiny_bbox(lat, lon), 3)
        for f in feats or []:
            g = f.get("geometry") or {}
            ring = None
            if g.get("type") == "Polygon":
                ring = g["coordinates"][0]
            elif g.get("type") == "MultiPolygon":
                ring = max((p[0] for p in g["coordinates"]), key=len)
            if ring and len(ring) >= 4:
                p = _props_text(f.get("properties"))
                return _res(True, {"anel_lonlat": ring, "props": p, "colecao": c["id"]},
                            f"DGT — {c['title'] or 'Cadastro predial'}", f"{DGT}/collections/{c['id']}")
    return _res(False, nota="sem cadastro geométrico disponível neste local")


# ------------------------------------------------------------------ altimetria
async def elevacoes(pontos: List[Tuple[float, float]]) -> Dict[str, Any]:
    """Cota (m) de cada ponto (lat, lon)."""
    if not pontos:
        return _res(False, nota="sem pontos")
    key = _gkey()
    if key:
        out: List[Optional[float]] = []
        ok = True
        for i in range(0, len(pontos), 256):
            loc = "|".join(f"{a:.7f},{b:.7f}" for a, b in pontos[i:i + 256])
            st, js = await _fetch("GET", f"{GMAPS}/elevation/json", {"locations": loc, "key": key}, None, "json")
            if not js or js.get("status") != "OK":
                ok = False
                break
            out += [r.get("elevation") for r in js.get("results", [])]
        if ok and len(out) == len(pontos):
            return _res(True, {"z": out, "resolucao_m": None}, "Google Elevation API", None,
                        "Altimetria de satélite (equivalente ao Google Earth): indicativa, não substitui o levantamento topográfico.")
    out = []
    for i in range(0, len(pontos), 100):
        loc = "|".join(f"{a:.6f},{b:.6f}" for a, b in pontos[i:i + 100])
        st, js = await _get(OPENTOPO, {"locations": loc}, conc=1)
        if not js or js.get("status") != "OK":
            return _res(False, nota="altimetria indisponível")
        out += [r.get("elevation") for r in js.get("results", [])]
        if i + 100 < len(pontos):
            await asyncio.sleep(1.05)   # limite público: 1 pedido/s
    return _res(True, {"z": out, "resolucao_m": 25}, "EU-DEM 25 m (Copernicus, via OpenTopoData)", OPENTOPO,
                "Modelo digital de terreno de 25 m: indicativo, não substitui o levantamento topográfico.")


# ------------------------------------------------------------------ via de acesso
_OVERPASS_KO = {"ate": 0.0}


async def via_reversa(lat: float, lon: float) -> Dict[str, Any]:
    """Rua mais próxima do ponto pela geocodificação inversa do Nominatim (com geometria) — repli do Overpass."""
    st, js = await _fetch("GET", f"{NOMINATIM}/reverse", {"lat": f"{lat:.7f}", "lon": f"{lon:.7f}", "zoom": 17, "format": "jsonv2",
                                                          "polygon_geojson": 1, "polygon_threshold": 0.00002,
                                                          "accept-language": "pt-PT"}, None, "json")
    if not isinstance(js, dict) or (js.get("category") or js.get("class")) != "highway":
        return _res(False, nota=f"geocodificação inversa sem rua ({st})")
    g = js.get("geojson") or {}
    if g.get("type") not in ("LineString", "MultiLineString"):
        return _res(False, nota="rua sem geometria")
    r = via_de_geometria(lat, lon, g, (js.get("address") or {}).get("road") or js.get("name"))
    if r["ok"]:
        r["fonte"] = "OpenStreetMap (Nominatim — rua mais próxima)"
    return r


def via_de_geometria(lat: float, lon: float, geom: Optional[dict], nome: Optional[str] = None) -> Dict[str, Any]:
    """Segmento da rua mais próximo do ponto, a partir da geometria GeoJSON devolvida pelo Nominatim."""
    if not geom:
        return _res(False, nota="sem geometria da rua")
    linhas = [geom["coordinates"]] if geom.get("type") == "LineString" else list(geom.get("coordinates") or [])
    best = None
    for ln in linhas:
        for a, b in zip(ln, ln[1:]):
            d, _t = _dist_seg((lat, lon), (a[1], a[0]), (b[1], b[0]))
            if best is None or d < best[0]:
                best = (d, (a[1], a[0]), (b[1], b[0]))
    if not best:
        return _res(False, nota="geometria da rua vazia")
    return _res(True, {"distancia_m": round(best[0], 1), "a": best[1], "b": best[2], "nome": nome, "tipo": "rua"},
                "OpenStreetMap (Nominatim — geometria da rua)", None)


async def via_proxima(lat: float, lon: float, raio_m: int = 80) -> Dict[str, Any]:
    q = (f"[out:json][timeout:15];way(around:{raio_m},{lat},{lon})[highway]"
         f"[highway!~\"footway|path|steps|cycleway|track|service\"];out geom 20;")
    if time.time() < _OVERPASS_KO["ate"]:
        return _res(False, nota="OpenStreetMap (Overpass) indisponível (falhou há pouco)")

    async def um(url):
        try:
            return url, await asyncio.wait_for(_fetch("GET", url, {"data": q}, None, "json"), 12)
        except Exception:  # noqa: BLE001
            return url, (0, None)
    js, diag = None, []
    for url, (st, j) in await asyncio.gather(*(um(u) for u in OVERPASS_ESPELHOS)):
        diag.append(f"{url.split('/')[2]}={st}")
        if j and js is None:
            js = j
    if not js:
        _OVERPASS_KO["ate"] = time.time() + 600
        return _res(False, nota="OpenStreetMap (Overpass) indisponível: " + "; ".join(diag))
    best = None
    for w in js.get("elements", []):
        g = w.get("geometry") or []
        for a, b in zip(g, g[1:]):
            d, t = _dist_seg((lat, lon), (a["lat"], a["lon"]), (b["lat"], b["lon"]))
            if best is None or d < best[0]:
                best = (d, a, b, w.get("tags", {}))
    if not best:
        return _res(False, nota="nenhuma via encontrada perto")
    d, a, b, tags = best
    return _res(True, {"distancia_m": round(d, 1), "a": (a["lat"], a["lon"]), "b": (b["lat"], b["lon"]),
                       "nome": tags.get("name"), "tipo": tags.get("highway")}, "OpenStreetMap (Overpass)", None)


def _dist_seg(p, a, b) -> Tuple[float, float]:
    """Distância (m) de p ao segmento ab, em aproximação local."""
    lat0 = math.radians(p[0])
    kx, ky = 111_320.0 * math.cos(lat0), 111_320.0
    px, py = 0.0, 0.0
    ax, ay = (a[1] - p[1]) * kx, (a[0] - p[0]) * ky
    bx, by = (b[1] - p[1]) * kx, (b[0] - p[0]) * ky
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy or 1e-9
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    cx, cy = ax + t * vx, ay + t * vy
    return math.hypot(cx - px, cy - py), t


# ------------------------------------------------------------------ ortofotomapa
async def ortofoto(lat: float, lon: float, meia_largura_m: float = 60.0, px: int = 1024) -> Dict[str, Any]:
    bbox = _bbox_around(lat, lon, meia_largura_m)
    st, img = await _get(f"{DGT}/collections/ortos-rgb/map", {"bbox": bbox, "width": px, "height": px, "f": "png"}, "bytes")
    if img and img[:4] == b"\x89PNG":
        return _res(True, {"png": img, "bbox": bbox}, "DGT — Ortofotomapa OrtoSat (30 cm)", f"{DGT}/collections/ortos-rgb")
    key = _gkey()
    if key:
        z = 20 if meia_largura_m <= 70 else 19
        st, img = await _fetch("GET", f"{GMAPS}/staticmap", {"center": f"{lat},{lon}", "zoom": z, "size": "640x640", "scale": 2,
                                                             "maptype": "satellite", "key": key}, None, "bytes")
        if img and img[:4] == b"\x89PNG":
            mpp = 156543.03392 * math.cos(math.radians(lat)) / (2 ** z) / 2   # m/píxel (scale=2)
            half = mpp * 640                                                   # 1280 px / 2
            return _res(True, {"png": img, "bbox": _bbox_around(lat, lon, half), "zoom": z}, "Google Maps (satélite)", None)
    return _res(False, nota="ortofotomapa indisponível")
